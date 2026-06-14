"""Chess vs Computer — tkinter GUI with a RAG-backed AI.

Board rendering fix: the board is redrawn IMMEDIATELY after every half-move
(yours and the computer's). The engine search runs on a background thread on a
copy of the position, so the UI never freezes and your move always appears on
the board before the computer starts thinking.

Frontend styling follows lichess / chess.com conventions: classic brown board,
dots on legal target squares, rings on capture targets, last-move and check
highlights, and rank/file coordinates.
"""

import math
import random
import threading
import tkinter as tk
from tkinter import ttk

import engine
from engine import (State, legal_moves, make_move, unmake_move, in_check,
                    find_king, game_status, to_san, search_best_move, opp)
from knowledge import KnowledgeBase
from analysis import analyze_game as run_game_analysis

# Player Clone Engine integration (a separate, self-contained subsystem under
# player_clones/). Imported lazily inside methods so the base app keeps starting
# instantly and still runs if the clone package is ever absent.
CLONE_MENU_LABEL = "Samay Clone"

import themes

SQ = 82
MARGIN = 30
BOARD_PX = SQ * 8 + MARGIN * 2


def _apply_board_theme(name):
    """Mirror a board theme into the module-level colour names redraw() uses."""
    global BOARD_THEME_NAME, LIGHT, DARK, LAST_LIGHT, LAST_DARK, SEL, CHECK, DOT
    if name not in themes.BOARD_THEMES:
        name = themes.DEFAULT_BOARD
    t = themes.BOARD_THEMES[name]
    BOARD_THEME_NAME = name
    LIGHT, DARK = t['light'], t['dark']
    LAST_LIGHT, LAST_DARK = t['last_light'], t['last_dark']
    SEL, CHECK, DOT = t['sel'], t['check'], t['dot']


def _apply_app_mode(mode):
    """Mirror an app palette (dark/light) into the module-level colour names."""
    global APP_MODE, BG, PANEL, TEXTBG, FG, MUTED, WARN, GOOD, BAD
    if mode not in themes.APP_PALETTES:
        mode = themes.DEFAULT_MODE
    p = themes.APP_PALETTES[mode]
    APP_MODE = mode
    BG, PANEL, TEXTBG = p['bg'], p['panel'], p['textbg']
    FG, MUTED = p['fg'], p['muted']
    WARN, GOOD, BAD = p['warn'], p['good'], p['bad']
    # keep the clone dashboards (DNA page, reports, mode dialog) in sync
    try:
        from player_clones.dashboard import theme as dash_theme
        dash_theme.apply_app_palette(p)
    except Exception:
        pass


_settings = themes.load_settings()
_apply_board_theme(_settings.get('board_theme', themes.DEFAULT_BOARD))
_apply_app_mode(_settings.get('app_mode', themes.DEFAULT_MODE))

GLYPH = {'P': '♟', 'N': '♞', 'B': '♝',
         'R': '♜', 'Q': '♛', 'K': '♚'}

ARENA_BG = '#080808'
ARENA_EDGE = '#22211f'
BOARD_FRAME = '#100b07'
BOARD_GLOW = '#6b421e'


def copy_state(s):
    c = State()
    c.board = s.board[:]
    c.turn = s.turn
    c.castling = s.castling
    c.ep = s.ep
    c.halfmove = s.halfmove
    return c


class ChessApp:
    def __init__(self, root):
        self.root = root
        root.title('Chess vs Computer — Python + RAG knowledge base')
        root.configure(bg=BG)
        root.title('Chess Arena - Python + RAG knowledge base')
        root.resizable(False, False)

        self.kb = KnowledgeBase()
        self.state = State()
        self.history = []        # {'move','undo','san','captured'}
        self.human = 'w'
        self.selected = -1
        self.targets = []
        self.ai_thinking = False
        self.analyzing = False
        self.game_over = False

        # --- Player Clone Engine state ---
        self.clone_provider = None        # lazily-built CloneProvider (mode view)
        self.mode_manager = None          # SamayModeManager (built once)
        self.clone_mode_key = 'real'      # casual | real | peak | adaptive
        self.clone_user_rating = 1200     # used by adaptive mode
        self.clone_loading = False
        self.clone_report_shown = False   # post-game report fires once per game
        self.commentator = None           # Samay banter engine (per game)
        self._clone_ready_cbs = []        # callbacks waiting on the clone to load

        self._build_ui()
        self.new_game()

    # ------------------------------------------------------------- theming
    def _btn(self, parent, text, command, kind='neutral', small=False):
        """Styled flat button with hover effect, coloured by the active theme."""
        base, hover, fg = themes.button_colors(APP_MODE, kind)
        b = tk.Button(parent, text=text, command=command, bg=base, fg=fg,
                      font=('Segoe UI', 9 if small else 10, 'bold'),
                      relief='flat', bd=0, padx=12 if small else 18,
                      pady=5 if small else 8,
                      activebackground=hover, activeforeground=fg,
                      cursor='hand2')
        b.bind('<Enter>', lambda e: b.configure(bg=hover))
        b.bind('<Leave>', lambda e: b.configure(bg=base))
        return b

    def _pill(self, parent, text, fg=None):
        return tk.Label(parent, text=text, bg=TEXTBG, fg=fg or FG,
                        font=('Segoe UI', 10, 'bold'), padx=13, pady=5)

    def open_theme_dialog(self):
        themes.open_theme_dialog(self.root, BOARD_THEME_NAME, APP_MODE,
                                 self.set_board_theme, self.set_app_mode)

    def set_board_theme(self, name):
        _apply_board_theme(name)
        self._save_ui_settings()
        self.redraw()

    def set_app_mode(self, mode):
        _apply_app_mode(mode)
        self._save_ui_settings()
        self._rebuild_ui()

    def _save_ui_settings(self):
        themes.save_settings({'board_theme': BOARD_THEME_NAME,
                              'app_mode': APP_MODE})

    def _rebuild_ui(self):
        """Recreate all widgets under the new palette; game state is untouched."""
        keep = (self.difficulty.get(), self.side.get(), self.opponent.get())
        for w in self.root.winfo_children():
            w.destroy()
        self.root.configure(bg=BG)
        self._build_ui()
        self.difficulty.set(keep[0])
        self.side.set(keep[1])
        self.opponent.set(keep[2])
        self._update_opponent_ui()
        self.redraw()
        self.update_status()

    # ------------------------------------------------- Player Clone helpers
    def _opponent_is_clone(self):
        return self.opponent.get() == CLONE_MENU_LABEL

    def _ensure_clone(self, on_ready=None):
        """Build the Samay clone on a background thread (import + analyze).

        The heavy part — the base clone with its repertoire snapshot — lives in
        a `SamayModeManager` built once; mode views over it are instant, so
        switching modes never reloads the data.
        """
        if self.clone_provider is not None:
            if on_ready:
                on_ready()
            return
        # Queue the callback so it still fires once the (possibly already
        # in-flight) background load finishes. Without this, a move made while
        # the clone is loading silently drops its on_ready and Samay never moves.
        if on_ready:
            self._clone_ready_cbs.append(on_ready)
        if self.clone_loading:
            return
        self.clone_loading = True
        self.set_status('Loading Samay clone…', WARN)

        def worker():
            error, manager = None, self.mode_manager
            if manager is None:
                try:
                    from player_clones.modes import SamayModeManager
                    manager = SamayModeManager()
                except Exception as e:    # network/data failure — degrade cleanly
                    manager, error = None, e

            def done():
                if not self.root.winfo_exists():
                    return
                self.clone_loading = False
                if manager is None:
                    self._clone_ready_cbs.clear()
                    self.set_status(f'Clone unavailable: {error}', BAD)
                    return
                self.mode_manager = manager
                self._apply_mode()
                cbs, self._clone_ready_cbs = self._clone_ready_cbs, []
                for cb in cbs:
                    cb()
            self.root.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_mode(self):
        """(Re)build the active mode view over the base clone — instant."""
        if self.mode_manager is None:
            return
        self.clone_provider = self.mode_manager.get(self.clone_mode_key,
                                                    self.clone_user_rating)
        self._update_opponent_ui()

    def _update_mode_label(self):
        if self.clone_provider is not None and self._opponent_is_clone():
            mode = getattr(self.clone_provider, 'mode', None)
            text = f'Mode: {mode.title} ({mode.strength})' if mode else ''
        else:
            text = ''
        self.mode_label.configure(text=text)

    def _update_opponent_ui(self):
        """Difficulty belongs to the classic computer; Samay has modes instead."""
        if self._opponent_is_clone():
            self.diff_label.grid_remove()
            self.difficulty.grid_remove()
            self.rag_header.configure(text='\U0001F3A4 Samay says')
        else:
            self.diff_label.grid()
            self.difficulty.grid()
            self.rag_header.configure(text='\U0001F4D6 Knowledge base (RAG)')
        self._update_mode_label()
        self._refresh_nameplates()

    def _on_opponent_change(self):
        self._update_opponent_ui()
        if self._opponent_is_clone():
            self._choose_mode(start_game=True)
        else:
            self.new_game()

    def _choose_mode(self, start_game=False):
        """Open the mode selection screen, then start/restart the game."""
        from player_clones.dashboard.mode_select import ask_mode
        choice = ask_mode(self.root, self.clone_mode_key, self.clone_user_rating)
        if choice is not None:
            self.clone_mode_key, self.clone_user_rating = choice
            if not self._opponent_is_clone():
                self.opponent.set(CLONE_MENU_LABEL)   # Mode… implies playing Samay
            self._apply_mode()
            self._ensure_clone()                      # warm up in the background
        if start_game or choice is not None:
            self.new_game()

    def show_samay_dna(self):
        from player_clones.dashboard import open_dna_page

        def ready():
            open_dna_page(self.root, self.clone_provider.dna())
        self._ensure_clone(on_ready=ready)

    def _show_clone_report(self, winner, text):
        """Open the post-game report after a game against the clone."""
        from player_clones.dashboard import open_post_game_report
        from player_clones.openings import classify_opening

        opening = classify_opening([h['san'] for h in self.history])
        if winner is None:
            res = f'Result: {text}'
        elif winner == self.human:
            res = f'You beat the clone — {text}'
        else:
            res = f'The clone won — {text}'
        # let the final board paint first
        self.root.after(300, lambda: open_post_game_report(
            self.root, self.clone_provider, opening, res))

    # ------------------------------------------------------------- UI build
    def _style_ttk(self):
        """Theme the ttk comboboxes to match the active palette."""
        style = ttk.Style(self.root)
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass
        style.configure('TCombobox', fieldbackground='#0f0f11', background='#242428',
                        foreground=FG, arrowcolor=FG, bordercolor='#36322e',
                        lightcolor='#36322e', darkcolor='#080808',
                        selectbackground=TEXTBG, selectforeground=FG)
        style.map('TCombobox',
                  fieldbackground=[('readonly', '#0f0f11')],
                  foreground=[('readonly', FG)])
        self.root.option_add('*TCombobox*Listbox.background', '#101012')
        self.root.option_add('*TCombobox*Listbox.foreground', FG)
        self.root.option_add('*TCombobox*Listbox.selectBackground', '#c58a3a')
        self.root.option_add('*TCombobox*Listbox.selectForeground', '#090909')

    def _card(self, parent, title):
        """A titled card section in the sidebar."""
        outer = tk.Frame(parent, bg=PANEL, highlightthickness=1,
                         highlightbackground='#24211d')
        outer.pack(fill='x', pady=(0, 12))
        tk.Label(outer, text=title.upper(), bg=PANEL, fg='#c9a56b',
                 font=('Segoe UI', 8, 'bold')).pack(anchor='w', padx=14,
                                                    pady=(10, 3))
        body = tk.Frame(outer, bg=PANEL)
        body.pack(fill='x', padx=14, pady=(0, 12))
        return body

    def _nameplate(self, parent):
        """A chess.com-style player bar: name, captured pieces, material edge."""
        f = tk.Frame(parent, bg='#101010', padx=12, pady=8,
                     highlightthickness=1, highlightbackground='#27221d')
        f.pack(fill='x', pady=(0, 8))
        avatar = tk.Label(f, text='♚', bg='#e8ded0', fg='#27211b',
                          font=('Segoe UI Symbol', 16, 'bold'),
                          width=2, height=1)
        avatar.pack(side='left', padx=(0, 9))
        name = tk.Label(f, text='', bg='#101010', fg=FG,
                        font=('Segoe UI', 11, 'bold'))
        name.pack(side='left')
        adv = tk.Label(f, text='', bg='#101010', fg=GOOD,
                       font=('Segoe UI', 10, 'bold'))
        adv.pack(side='right')
        caps = tk.Label(f, text='', bg='#101010', fg=MUTED,
                        font=('Segoe UI Symbol', 13))
        caps.pack(side='right', padx=8)
        return {'frame': f, 'avatar': avatar, 'name': name, 'caps': caps, 'adv': adv}

    def _nav_button(self, parent, icon, label, active=False, command=None):
        bg = '#1b1b1e' if active else '#101012'
        fg = '#f0d29a' if active else MUTED
        b = tk.Button(parent, text=f'{icon}\n{label}', command=command,
                      bg=bg, fg=fg, activebackground='#252529',
                      activeforeground='#f0d29a', relief='flat', bd=0,
                      font=('Segoe UI', 8, 'bold'), width=11, pady=8,
                      cursor='hand2')
        b.pack(side='left', fill='x', expand=True)
        return b

    def _soft_panel(self, parent, bg='#101622', padx=12, pady=12):
        f = tk.Frame(parent, bg=bg, padx=padx, pady=pady,
                     highlightthickness=1, highlightbackground='#242b3f')
        return f

    def _metric_card(self, parent, title, value, sub='', wide=False):
        card = self._soft_panel(parent, bg='#121929', padx=16, pady=14)
        card.pack(side='left', fill='both', expand=True,
                  padx=(0, 10 if not wide else 0))
        tk.Label(card, text=title, bg='#121929', fg=MUTED,
                 font=('Segoe UI', 10)).pack(anchor='w')
        tk.Label(card, text=value, bg='#121929', fg=FG,
                 font=('Segoe UI', 24, 'bold')).pack(anchor='w', pady=(10, 3))
        if sub:
            tk.Label(card, text=sub, bg='#121929', fg=MUTED,
                     font=('Segoe UI', 9)).pack(anchor='w')
        return card

    def _dna_meter(self, parent, icon, label, value):
        row = tk.Frame(parent, bg='#101622')
        row.pack(fill='x', pady=8)
        tk.Label(row, text=icon, bg='#101622', fg='#a895ff',
                 font=('Segoe UI Symbol', 12)).pack(side='left')
        tk.Label(row, text=label, bg='#101622', fg=FG,
                 font=('Segoe UI', 9)).pack(side='left', padx=8)
        tk.Label(row, text=f'{value}%', bg='#101622', fg=MUTED,
                 font=('Segoe UI', 9)).pack(side='right')
        bar = tk.Canvas(parent, width=150, height=8, bg='#101622',
                        highlightthickness=0)
        bar.pack(anchor='e', pady=(0, 3))
        bar.create_rectangle(0, 2, 150, 7, fill='#242b3f', outline='')
        bar.create_rectangle(0, 2, int(150 * value / 100), 7,
                             fill='#8f74ff', outline='')

    def _select_computer(self):
        self.opponent.set('Computer')
        self._on_opponent_change()

    def _select_samay(self):
        self.opponent.set(CLONE_MENU_LABEL)
        self._on_opponent_change()

    def _build_arena_ui(self):
        """Modern dashboard layout based on the supplied reference image."""
        self.root.title('Chess Arena')
        self.root.configure(bg='#070b14')

        title = tk.Frame(self.root, bg='#070b14', height=52)
        title.pack(fill='x', padx=18)
        title.pack_propagate(False)
        tk.Label(title, text='♘', bg='#070b14', fg='#8f74ff',
                 font=('Segoe UI Symbol', 18, 'bold')).pack(side='left')
        tk.Label(title, text='Chess Arena', bg='#070b14', fg=FG,
                 font=('Segoe UI', 11, 'bold')).pack(side='left', padx=(10, 12))
        tk.Label(title, text='•  Engine, Samay clone, analysis',
                 bg='#070b14', fg=MUTED, font=('Segoe UI', 10)
                 ).pack(side='left')
        for glyph in ('×', '□', '−'):
            tk.Label(title, text=glyph, bg='#070b14', fg=MUTED,
                     font=('Segoe UI', 14), width=4).pack(side='right')

        main = tk.Frame(self.root, bg='#070b14')
        main.pack(fill='both', expand=True, padx=18, pady=(0, 18))

        left = tk.Frame(main, bg='#070b14')
        left.pack(side='left', anchor='n', padx=(0, 12))

        header = self._soft_panel(left, bg='#101622', padx=14, pady=12)
        header.pack(fill='x', pady=(0, 12))
        tk.Label(header, text='🤖', bg='#1b2334', fg=FG,
                 font=('Segoe UI Symbol', 20), width=3).pack(side='left')
        htxt = tk.Frame(header, bg='#101622')
        htxt.pack(side='left', padx=12)
        self.match_title = tk.Label(htxt, text='Playing vs Computer',
                                    bg='#101622', fg=FG,
                                    font=('Segoe UI', 12, 'bold'))
        self.match_title.pack(anchor='w')
        self.match_subtitle = tk.Label(htxt, text='Medium  •  Elo 1500',
                                       bg='#101622', fg='#a895ff',
                                       font=('Segoe UI', 10))
        self.match_subtitle.pack(anchor='w')
        self._btn(header, '+ New Game', self.new_game,
                  kind='primary').pack(side='right', padx=(8, 0))
        self._btn(header, 'Analysis', self.analyze_game,
                  kind='success').pack(side='right', padx=(8, 0))
        self._btn(header, 'Settings', self.open_theme_dialog,
                  kind='neutral').pack(side='right', padx=(8, 0))
        self._btn(header, 'DNA', self.show_samay_dna,
                  kind='accent').pack(side='right', padx=(8, 0))
        self._btn(header, 'Mode', lambda: self._choose_mode(),
                  kind='info').pack(side='right', padx=(8, 0))
        self._btn(header, 'Play vs Samay', self._select_samay,
                  kind='primary').pack(side='right', padx=(8, 0))
        self._btn(header, 'Computer', self._select_computer,
                  kind='neutral').pack(side='right', padx=(8, 0))

        boardrow = tk.Frame(left, bg='#070b14')
        boardrow.pack(fill='x')

        evalbar = self._soft_panel(boardrow, bg='#101622', padx=14, pady=14)
        evalbar.pack(side='left', fill='y', padx=(0, 12))
        tk.Label(evalbar, text='+0.8', bg='#101622', fg=FG,
                 font=('Segoe UI', 9)).pack(pady=(78, 10))
        evcan = tk.Canvas(evalbar, width=34, height=500, bg='#101622',
                          highlightthickness=0)
        evcan.pack()
        evcan.create_rectangle(12, 0, 24, 500, fill='#222a3c', outline='')
        evcan.create_rectangle(12, 155, 24, 500, fill='#f6f6fb', outline='')
        evcan.create_rectangle(12, 312, 24, 316, fill='#8f74ff', outline='')
        tk.Label(evalbar, text='0.0', bg='#101622', fg=FG,
                 font=('Segoe UI', 9)).pack(pady=(10, 0))
        tk.Label(evalbar, text='-0.8', bg='#101622', fg=FG,
                 font=('Segoe UI', 9)).pack(pady=(135, 0))

        boardcol = tk.Frame(boardrow, bg='#070b14')
        boardcol.pack(side='left')
        boardwrap = tk.Frame(boardcol, bg='#101622', padx=0, pady=0,
                             highlightthickness=1,
                             highlightbackground='#242b3f')
        boardwrap.pack()
        self.canvas = tk.Canvas(boardwrap, width=BOARD_PX, height=BOARD_PX,
                                bg=BOARD_FRAME, highlightthickness=0)
        self.canvas.pack()
        self.canvas.bind('<Button-1>', self.on_click)

        player = self._soft_panel(boardcol, bg='#101622', padx=14, pady=14)
        player.pack(fill='x', pady=(12, 0))
        self.bottom_plate = self._nameplate(player)
        self.top_plate = self._nameplate(tk.Frame(self.root))
        self.top_plate['frame'].pack_forget()
        self.cap_ai = self.top_plate['caps']
        self.cap_human = self.bottom_plate['caps']

        right = tk.Frame(main, bg='#070b14', width=520)
        right.pack(side='left', fill='y', anchor='n')
        right.pack_propagate(False)

        tabs = self._soft_panel(right, bg='#101622', padx=12, pady=0)
        tabs.pack(fill='x', pady=(0, 12))
        for label, active in (('Moves', True), ('Analysis', False), ('DNA', False)):
            tk.Label(tabs, text=label, bg='#101622',
                     fg=('#a895ff' if active else MUTED),
                     font=('Segoe UI', 11, 'bold'), padx=24, pady=17
                     ).pack(side='left')
        tk.Label(tabs, text='≡', bg='#151b2b', fg=FG,
                 font=('Segoe UI', 14), padx=12, pady=8).pack(side='right', pady=10)

        metrics = self._soft_panel(right, bg='#101622', padx=12, pady=12)
        metrics.pack(fill='x', pady=(0, 8))
        self._metric_card(metrics, 'Evaluation', '+0.8', 'White is better')
        self._metric_card(metrics, 'Best Move', '♞  Nf3', 'Why?', wide=True)

        grid = tk.Frame(right, bg='#070b14')
        grid.pack(fill='both', expand=True)
        leftcol = tk.Frame(grid, bg='#070b14', width=360)
        leftcol.pack(side='left', fill='both', expand=True, padx=(0, 8))
        dnacol = tk.Frame(grid, bg='#070b14', width=230)
        dnacol.pack(side='left', fill='y')

        moves = self._soft_panel(leftcol, bg='#101622', padx=12, pady=12)
        moves.pack(fill='x', pady=(0, 8))
        tk.Label(moves, text='Move List', bg='#101622', fg=FG,
                 font=('Segoe UI', 11)).pack(anchor='w', pady=(0, 8))
        self.move_text = tk.Text(moves, height=5, width=34, bg='#151b2b',
                                 fg=FG, font=('Consolas', 10), relief='flat',
                                 wrap='none', padx=10, pady=6,
                                 state='disabled')
        self.move_text.pack(fill='x')
        self.move_text.tag_configure('num', foreground=MUTED)
        self.move_text.tag_configure('last', foreground='#a895ff',
                                     background='#242a48',
                                     font=('Consolas', 10, 'bold'))

        chat = self._soft_panel(leftcol, bg='#101622', padx=12, pady=12)
        chat.pack(fill='both', expand=True)
        self.rag_header = tk.Label(chat, text='☯  Samay Commentary',
                                   bg='#101622', fg='#a895ff',
                                   font=('Segoe UI', 10, 'bold'), anchor='w')
        self.rag_header.pack(fill='x', pady=(0, 10))
        self.rag_text = tk.Text(chat, height=10, bg='#101622', fg=FG,
                                font=('Segoe UI', 9), relief='flat',
                                wrap='word', padx=0, pady=0, state='disabled')
        self.rag_text.pack(fill='both', expand=True)
        ask = tk.Frame(chat, bg='#151b2b', highlightthickness=1,
                       highlightbackground='#2a3248')
        ask.pack(fill='x', pady=(10, 0))
        tk.Label(ask, text='Ask Samay anything...', bg='#151b2b', fg=MUTED,
                 font=('Segoe UI', 10), padx=10, pady=10).pack(side='left')
        tk.Label(ask, text='➤', bg='#5c57d8', fg='white',
                 font=('Segoe UI Symbol', 12), padx=12, pady=8).pack(side='right')

        dna = self._soft_panel(dnacol, bg='#101622', padx=16, pady=16)
        dna.pack(fill='both', expand=True)
        tk.Label(dna, text='PLAYER DNA', bg='#101622', fg=FG,
                 font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        tk.Frame(dna, bg='#242b3f', height=1).pack(fill='x', pady=12)
        # Real numbers measured from Samay's full Chess.com archive (see
        # player_clones/samay_profile.py). This is the sidebar preview; the
        # full, live-computed fingerprint opens via "View Full DNA" below.
        from player_clones.samay_profile import SAMAY_STYLE_PRIOR as _sp
        self._dna_meter(dna, '🔥', 'Aggression', _sp['aggression'])
        self._dna_meter(dna, '⚔', 'Tactics', _sp['tactical'])
        self._dna_meter(dna, '▣', 'Risk', _sp['risk'])
        self._dna_meter(dna, '♛', 'Endgames', _sp['endgame'])
        tk.Label(dna, text='Style', bg='#101622', fg=MUTED,
                 font=('Segoe UI', 10)).pack(anchor='w', pady=(16, 6))
        tk.Label(dna, text='Chaos Merchant', bg='#2a2554', fg='#b8a8ff',
                 font=('Segoe UI', 10, 'bold'), padx=10, pady=5).pack(anchor='w')
        tk.Label(dna, text='Loves complications and\nunpredictable positions.',
                 bg='#101622', fg=MUTED, font=('Segoe UI', 9),
                 justify='left').pack(anchor='w', pady=10)
        tk.Button(dna, text='View Full DNA  →', command=self.show_samay_dna,
                  bg='#121929', fg=FG, activebackground='#1b2334',
                  relief='flat', bd=0, font=('Segoe UI', 10),
                  padx=18, pady=9, cursor='hand2').pack(fill='x', side='bottom')

        controls = self._soft_panel(right, bg='#101622', padx=12, pady=12)
        controls.pack(fill='x', pady=(8, 0))
        self._btn(controls, '↶ Undo', self.undo, kind='neutral').pack(side='left')
        self._btn(controls, '▥ Analysis', self.analyze_game,
                  kind='neutral').pack(side='left', padx=8)
        self._btn(controls, '◉ Theme', self.open_theme_dialog,
                  kind='neutral').pack(side='left')
        self._btn(controls, '⚙ Settings', self.open_theme_dialog,
                  kind='neutral').pack(side='left', padx=8)

        playback = tk.Frame(right, bg='#101622')
        playback.pack(fill='x', padx=12, pady=(8, 0))
        for label, active in (('⏮', False), ('◀', False), ('▶', True),
                              ('▶', False), ('⏭', False)):
            tk.Button(playback, text=label, bg=('#5c57d8' if active else '#151b2b'),
                      fg='white', activebackground='#716cff',
                      relief='flat', bd=0, font=('Segoe UI Symbol', 13, 'bold'),
                      width=7, pady=10, cursor='hand2'
                      ).pack(side='left', padx=5, fill='x', expand=True)

        setup = tk.Frame(self.root, bg='#070b14')
        self.opponent = ttk.Combobox(setup, values=['Computer', CLONE_MENU_LABEL],
                                     state='readonly', width=13)
        self.opponent.set('Computer')
        self.opponent.bind('<<ComboboxSelected>>',
                           lambda e: self._on_opponent_change())
        self.diff_label = tk.Label(setup, text='Difficulty', bg='#070b14', fg=MUTED)
        self.difficulty = ttk.Combobox(setup, values=['easy', 'medium', 'hard'],
                                       state='readonly', width=13)
        self.difficulty.set('medium')
        self.difficulty.bind('<<ComboboxSelected>>',
                             lambda e: self._refresh_nameplates())
        self.playas_label = tk.Label(setup, text='Play as', bg='#070b14', fg=MUTED)
        self.side = ttk.Combobox(setup, values=['White', 'Black'],
                                 state='readonly', width=13)
        self.side.set('White')
        self.side.bind('<<ComboboxSelected>>', lambda e: self.new_game())
        self.mode_label = tk.Label(setup, text='', bg='#070b14', fg=GOOD)

        self.status = tk.Label(header, text='Your move', bg='#101622', fg=FG)
        self._refresh_nameplates()

    def _build_ui(self):
        self._style_ttk()
        self._build_arena_ui()
        return
        self.root.title('Chess Studio — engine • Samay clone • analysis')

        # ---------- header bar ---------- #
        header = tk.Frame(self.root, bg=PANEL)
        header.pack(fill='x')
        tk.Frame(header, bg='#5a67d8', height=3).pack(fill='x')   # accent strip
        hin = tk.Frame(header, bg=PANEL)
        hin.pack(fill='x', padx=16, pady=9)
        tk.Label(hin, text='♞ Chess Studio', bg=PANEL, fg=FG,
                 font=('Segoe UI', 15, 'bold')).pack(side='left')
        tk.Label(hin, text='play the engine — or play Samay', bg=PANEL,
                 fg=MUTED, font=('Segoe UI', 9)).pack(side='left',
                                                      padx=12, pady=(5, 0))
        self._btn(hin, '🎨 Theme', self.open_theme_dialog,
                  kind='neutral', small=True).pack(side='right')
        self.status = tk.Label(hin, text='Your move', bg=TEXTBG, fg=FG,
                               font=('Segoe UI', 10, 'bold'), padx=14, pady=5)
        self.status.pack(side='right', padx=10)

        main = tk.Frame(self.root, bg=BG)
        main.pack(fill='both', expand=True)

        # ---------- left: nameplates + board ---------- #
        left = tk.Frame(main, bg=BG)
        left.pack(side='left', padx=(16, 8), pady=10, anchor='n')

        self.top_plate = self._nameplate(left)
        boardwrap = tk.Frame(left, bg=PANEL, padx=5, pady=5)
        boardwrap.pack()
        self.canvas = tk.Canvas(boardwrap, width=BOARD_PX, height=BOARD_PX,
                                bg=PANEL, highlightthickness=0)
        self.canvas.pack()
        self.canvas.bind('<Button-1>', self.on_click)
        self.bottom_plate = self._nameplate(left)
        self.cap_ai = self.top_plate['caps']        # pieces the opponent took
        self.cap_human = self.bottom_plate['caps']  # pieces you took

        # ---------- right: sidebar cards ---------- #
        panel = tk.Frame(main, bg=BG)
        panel.pack(side='left', fill='y', padx=(8, 16), pady=10, anchor='n')

        # game controls
        ctl = self._card(panel, 'Game')
        self._btn(ctl, 'New Game', self.new_game,
                  kind='primary').pack(side='left')
        self._btn(ctl, 'Undo', self.undo,
                  kind='neutral').pack(side='left', padx=8)
        self._btn(ctl, 'Analyze', self.analyze_game,
                  kind='success').pack(side='left')

        # match setup
        setup = self._card(panel, 'Match')
        setup.columnconfigure(1, weight=1)
        tk.Label(setup, text='Opponent', bg=PANEL, fg=MUTED,
                 font=('Segoe UI', 10)).grid(row=0, column=0, sticky='w')
        self.opponent = ttk.Combobox(setup, values=['Computer', CLONE_MENU_LABEL],
                                     state='readonly', width=13)
        self.opponent.set('Computer')
        self.opponent.grid(row=0, column=1, sticky='w', padx=8, pady=3)
        self.opponent.bind('<<ComboboxSelected>>',
                           lambda e: self._on_opponent_change())
        obtns = tk.Frame(setup, bg=PANEL)
        obtns.grid(row=0, column=2, sticky='e')
        self._btn(obtns, 'Mode…', lambda: self._choose_mode(),
                  kind='info', small=True).pack(side='left')
        self._btn(obtns, 'DNA', self.show_samay_dna,
                  kind='accent', small=True).pack(side='left', padx=(6, 0))

        # difficulty applies to the classic computer only — hidden in Samay mode
        # (Samay's strength comes from his mode: Casual / Real / Peak / Adaptive)
        self.diff_label = tk.Label(setup, text='Difficulty', bg=PANEL, fg=MUTED,
                                   font=('Segoe UI', 10))
        self.diff_label.grid(row=1, column=0, sticky='w')
        self.difficulty = ttk.Combobox(setup, values=['easy', 'medium', 'hard'],
                                       state='readonly', width=13)
        self.difficulty.set('medium')
        self.difficulty.grid(row=1, column=1, sticky='w', padx=8, pady=3)
        self.difficulty.bind('<<ComboboxSelected>>',
                             lambda e: self._refresh_nameplates())

        self.playas_label = tk.Label(setup, text='Play as', bg=PANEL, fg=MUTED,
                                     font=('Segoe UI', 10))
        self.playas_label.grid(row=2, column=0, sticky='w')
        self.side = ttk.Combobox(setup, values=['White', 'Black'],
                                 state='readonly', width=13)
        self.side.set('White')
        self.side.grid(row=2, column=1, sticky='w', padx=8, pady=3)
        self.side.bind('<<ComboboxSelected>>', lambda e: self.new_game())

        self.mode_label = tk.Label(setup, text='', bg=PANEL, fg=GOOD,
                                   font=('Segoe UI', 9, 'bold'), anchor='w')
        self.mode_label.grid(row=3, column=0, columnspan=3, sticky='w',
                             pady=(4, 0))

        # move list
        moves = self._card(panel, 'Moves')
        mwrap = tk.Frame(moves, bg=TEXTBG)
        mwrap.pack(fill='x')
        mscroll = tk.Scrollbar(mwrap, width=10)
        mscroll.pack(side='right', fill='y')
        self.move_text = tk.Text(mwrap, height=9, width=38, bg=TEXTBG, fg=FG,
                                 font=('Consolas', 10), relief='flat',
                                 wrap='none', padx=10, pady=6,
                                 state='disabled', yscrollcommand=mscroll.set)
        self.move_text.pack(side='left', fill='x', expand=True)
        mscroll.config(command=self.move_text.yview)
        self.move_text.tag_configure('num', foreground=MUTED)
        self.move_text.tag_configure('last', foreground=GOOD,
                                     font=('Consolas', 10, 'bold'))

        # commentary / knowledge
        self.rag_header_card = self._card(panel, 'Commentary')
        self.rag_header = tk.Label(self.rag_header_card,
                                   text='\U0001F4D6 Knowledge base (RAG)',
                                   bg=PANEL, fg=MUTED,
                                   font=('Segoe UI', 9, 'bold'), anchor='w')
        self.rag_header.pack(fill='x', pady=(0, 2))
        self.rag_text = tk.Text(self.rag_header_card, height=9, width=44,
                                bg=TEXTBG, fg=FG, font=('Segoe UI', 9),
                                relief='flat', wrap='word', padx=10, pady=6,
                                state='disabled')
        self.rag_text.pack(fill='x')

        self._refresh_nameplates()

    def _refresh_nameplates(self):
        if self._opponent_is_clone():
            opp_name = (self.clone_provider.display_name
                        if self.clone_provider else 'Samay Clone')
            top = f'\U0001F3A4 {opp_name}'
            if hasattr(self, 'match_title'):
                self.match_title.configure(text=f'Playing vs {opp_name}')
                mode = getattr(self.clone_provider, 'mode', None)
                subtitle = f'{mode.title}  •  {mode.strength}' if mode else 'Samay Raina style clone'
                self.match_subtitle.configure(text=subtitle)
        else:
            top = f'\U0001F916 Computer ({self.difficulty.get()})'
            if hasattr(self, 'match_title'):
                self.match_title.configure(text='Playing vs Computer')
                self.match_subtitle.configure(
                    text=f'{self.difficulty.get().title()}  •  Elo 1500')
        you_side = 'White' if self.human == 'w' else 'Black'
        self.top_plate['name'].configure(text=top)
        self.bottom_plate['name'].configure(text=f'\U0001F9D1 You ({you_side})')

    # ------------------------------------------------------------- drawing
    def display_to_board(self, d):
        return d if self.human == 'w' else 63 - d

    def _wood_square(self, cv, x0, y0, fill, dark, seed):
        """Draw a clean flat board square."""
        cv.create_rectangle(x0, y0, x0 + SQ, y0 + SQ, fill=fill, outline='')

    def _draw_piece(self, cv, p, cx, cy):
        """Layered text rendering gives the unicode pieces a carved-token feel."""
        size = 44
        if p[0] == 'w':
            cv.create_text(cx + 3, cy + 4, text=GLYPH[p[1]],
                           font=('Segoe UI Symbol', size), fill='#6e4920')
            cv.create_text(cx + 1, cy + 2, text=GLYPH[p[1]],
                           font=('Segoe UI Symbol', size), fill='#fff1c7')
            cv.create_text(cx - 1, cy - 1, text=GLYPH[p[1]],
                           font=('Segoe UI Symbol', size), fill='#c58a3a')
        else:
            cv.create_text(cx + 3, cy + 4, text=GLYPH[p[1]],
                           font=('Segoe UI Symbol', size), fill='#000000')
            cv.create_text(cx + 1, cy + 2, text=GLYPH[p[1]],
                           font=('Segoe UI Symbol', size), fill='#595046')
            cv.create_text(cx - 1, cy - 1, text=GLYPH[p[1]],
                           font=('Segoe UI Symbol', size), fill='#161310')

    def redraw(self):
        cv = self.canvas
        cv.delete('all')
        cv.create_rectangle(0, 0, BOARD_PX, BOARD_PX, fill=BOARD_FRAME,
                            outline='')
        cv.create_rectangle(MARGIN - 4, MARGIN - 4,
                            MARGIN + 8 * SQ + 4, MARGIN + 8 * SQ + 4,
                            outline='#3b2412', width=4)
        last = self.history[-1]['move'] if self.history else None
        check_sq = find_king(self.state.board, self.state.turn) \
            if in_check(self.state, self.state.turn) else -1

        for d in range(64):
            i = self.display_to_board(d)
            r, c = d >> 3, d & 7
            x0, y0 = MARGIN + c * SQ, MARGIN + r * SQ
            dark = ((i >> 3) + (i & 7)) % 2
            fill = DARK if dark else LIGHT
            if last and i in (last.frm, last.to):
                fill = LAST_DARK if dark else LAST_LIGHT
            if i == self.selected:
                fill = SEL
            self._wood_square(cv, x0, y0, fill, dark, i)
            if i == check_sq:
                cv.create_oval(x0 + 6, y0 + 6, x0 + SQ - 6, y0 + SQ - 6,
                               fill=CHECK, outline='#ffded5', width=2,
                               stipple='gray50')
            p = self.state.board[i]
            if p:
                cx, cy = x0 + SQ / 2, y0 + SQ / 2
                self._draw_piece(cv, p, cx, cy)
            if any(m.to == i for m in self.targets):
                if p:  # capture target: ring
                    cv.create_oval(x0 + 5, y0 + 5, x0 + SQ - 5, y0 + SQ - 5,
                                   outline=DOT, width=5)
                else:  # quiet move: dot
                    q = SQ * 0.16
                    cv.create_oval(x0 + SQ / 2 - q, y0 + SQ / 2 - q,
                                   x0 + SQ / 2 + q, y0 + SQ / 2 + q,
                                   fill=DOT, outline='#e9f3c2', width=1,
                                   stipple='gray50')

        files = 'abcdefgh' if self.human == 'w' else 'hgfedcba'
        ranks = '87654321' if self.human == 'w' else '12345678'
        for k in range(8):
            cv.create_text(MARGIN + k * SQ + SQ / 2, BOARD_PX - MARGIN / 2,
                           text=files[k], fill='#dac9b4',
                           font=('Segoe UI', 10, 'bold'))
            cv.create_text(MARGIN / 2, MARGIN + k * SQ + SQ / 2,
                           text=ranks[k], fill='#dac9b4',
                           font=('Segoe UI', 10, 'bold'))

        self._update_move_list()
        self._update_captured()
        self._update_rag_panel(self._last_ai_note)
        # paint right now, before any engine work begins
        self.root.update_idletasks()

    def _update_move_list(self):
        """Two-column move table; the latest move is highlighted."""
        t = self.move_text
        t.configure(state='normal')
        t.delete('1.0', 'end')
        n = len(self.history)
        for k in range(0, n, 2):
            num = k // 2 + 1
            white_san = self.history[k]['san']
            black_san = self.history[k + 1]['san'] if k + 1 < n else ''
            t.insert('end', f'{num:>3}. ', 'num')
            t.insert('end', f'{white_san:<10}',
                     'last' if k == n - 1 else '')
            t.insert('end', f'{black_san}\n',
                     'last' if k + 1 == n - 1 else '')
        t.see('end')
        t.configure(state='disabled')

    def _update_captured(self):
        mine, theirs = '', ''
        my_gain = their_gain = 0
        for h in self.history:
            cap = h['captured']
            if not cap:
                continue
            if cap[0] == self.human:
                theirs += GLYPH[cap[1]]
                their_gain += engine.VAL[cap[1]]
            else:
                mine += GLYPH[cap[1]]
                my_gain += engine.VAL[cap[1]]
        self.cap_human.configure(text=mine or '—')
        self.cap_ai.configure(text=theirs or '—')
        # material edge shown on the leading player's nameplate (pawn units)
        diff = (my_gain - their_gain) // 100
        self.bottom_plate['adv'].configure(text=f'+{diff}' if diff > 0 else '')
        self.top_plate['adv'].configure(text=f'+{-diff}' if diff < 0 else '')

    def _set_rag(self, text):
        self.rag_text.configure(state='normal')
        self.rag_text.delete('1.0', 'end')
        self.rag_text.insert('1.0', text)
        self.rag_text.configure(state='disabled')

    def _update_rag_panel(self, ai_note=None):
        lines = []
        if ai_note:
            lines.append(ai_note)
            lines.append('')
        retrieved = self.kb.retrieve(self.state)
        if retrieved:
            lines.append('Current position retrieved from the corpus:')
            for bm in retrieved[:4]:
                src = '; '.join(bm.sources[:2])
                if len(bm.sources) > 2:
                    src += f' (+{len(bm.sources) - 2} more)'
                lines.append(f'  • {bm.san}  — {src}')
        else:
            lines.append('Position not in the knowledge base — '
                         'the engine relies on search from here.')
        self._set_rag('\n'.join(lines))

    # ------------------------------------------------------------- status
    def set_status(self, text, color=None):
        # default resolved at call time so dark/light switches apply instantly
        self.status.configure(text=text, fg=color or FG)

    def update_status(self):
        over, winner, text = game_status(self.state)
        if over:
            self.game_over = True
            foe = self.clone_provider.display_name \
                if (self._opponent_is_clone() and self.clone_provider) else 'computer'
            if winner is None:
                self.set_status(f'\U0001F91D {text}', GOOD)
            elif winner == self.human:
                self.set_status(f'\U0001F389 {text} — you win!', GOOD)
            else:
                self.set_status(f'\U0001F480 {text} — {foe} wins.', BAD)
            if self._opponent_is_clone() and self.clone_provider \
                    and not self.clone_report_shown:
                self.clone_report_shown = True
                if self.commentator is not None:
                    clone_won = None if winner is None else (winner != self.human)
                    self._last_ai_note = ('\U0001F3A4 "' +
                                          self.commentator.on_game_over(clone_won) + '"')
                    self._update_rag_panel(self._last_ai_note)
                self._show_clone_report(winner, text)
            return
        if self.state.turn == self.human:
            if in_check(self.state, self.state.turn):
                self.set_status('⚠ You are in check!', WARN)
            else:
                self.set_status('Your move')
        else:
            self.set_status('Computer is thinking…', WARN)

    # ------------------------------------------------------------- gameplay
    def apply_move(self, m, ai_note=None):
        san = to_san(self.state, m)
        captured = (opp(m.piece[0]) + 'P') if m.flag == 'ep' else self.state.board[m.to]
        undo = make_move(self.state, m)
        self.history.append({'move': m, 'undo': undo, 'san': san, 'captured': captured})
        self.selected = -1
        self.targets = []
        self._last_ai_note = ai_note
        self.redraw()                      # board updates after EVERY move
        self.update_status()

    def on_click(self, event):
        if (self.ai_thinking or self.analyzing or self.game_over
                or self.state.turn != self.human):
            return
        c = int((event.x - MARGIN) // SQ)
        r = int((event.y - MARGIN) // SQ)
        if not (0 <= r < 8 and 0 <= c < 8):
            return
        i = self.display_to_board(r * 8 + c)
        chosen = [m for m in self.targets if m.to == i]
        if chosen:
            if chosen[0].promo:
                self.promotion_dialog(chosen)
                return
            self.human_move(chosen[0])
            return
        p = self.state.board[i]
        if p and p[0] == self.human:
            if i == self.selected:
                self.selected, self.targets = -1, []
            else:
                self.selected = i
                self.targets = [m for m in legal_moves(self.state) if m.frm == i]
        else:
            self.selected, self.targets = -1, []
        self.redraw()

    def human_move(self, m):
        self.apply_move(m)
        if not self.game_over:
            self.schedule_ai()

    def schedule_ai(self):
        # Player-clone opponent takes a different path; if it is still loading,
        # retry once it is ready.
        if self._opponent_is_clone():
            if self.clone_provider is None:
                self._ensure_clone(on_ready=self.schedule_ai)
                return
            self._schedule_clone_ai()
            return

        self.ai_thinking = True
        self.set_status('Computer is thinking…', WARN)
        level = self.difficulty.get()
        move_number = len(self.history) // 2 + 1
        snapshot = copy_state(self.state)   # search a copy; UI state stays untouched

        def worker():
            book = self.kb.pick_book_move(snapshot, level, move_number)
            if book is not None:
                result = ('book', book.uci, book.sources)
            else:
                m, score, nodes = search_best_move(snapshot, level)
                result = ('search', m.uci() if m else None, (score, nodes, level))
            self.root.after(0, lambda: self.on_ai_done(result))

        threading.Thread(target=worker, daemon=True).start()

    def _schedule_clone_ai(self):
        """Ask the Samay clone for its move (off the UI thread)."""
        self.ai_thinking = True
        provider = self.clone_provider
        self.set_status(f'{provider.display_name} is thinking…', WARN)
        snapshot = copy_state(self.state)

        def worker():
            try:
                decision = provider.decide(snapshot)
                result = ('clone',
                          decision.move.uci() if decision.move else None,
                          (decision.source, decision.style_score, decision.eval_cp,
                           decision.contributions))
            except Exception as e:                 # never leave Samay hung
                self.root.after(0, lambda e=e: self._on_ai_error(e))
                return
            self.root.after(0, lambda: self.on_ai_done(result))

        threading.Thread(target=worker, daemon=True).start()

    def _on_ai_error(self, error):
        if not self.root.winfo_exists():
            return
        self.ai_thinking = False
        self.set_status(f'Samay could not move: {error}', BAD)

    def on_ai_done(self, result):
        if not self.root.winfo_exists():   # window closed while AI was thinking
            return
        self.ai_thinking = False
        kind, uci, info = result
        if uci is None:
            self.update_status()
            return
        move = next((m for m in legal_moves(self.state) if m.uci() == uci), None)
        if move is None:
            self.update_status()
            return
        if kind == 'book':
            src = '; '.join(info[:2])
            note = f'\U0001F4D6 Book move {to_san(self.state, move)} — retrieved from: {src}'
        elif kind == 'clone':
            source, style_score, eval_cp, contribs = info
            san = to_san(self.state, move)
            if self.commentator is not None:
                banter = self.commentator.on_clone_move(san, source,
                                                        contribs or {}, eval_cp)
                note = f'\U0001F3A4 "{banter}"'
            else:
                note = f'\U0001F9EC {self.clone_provider.display_name}: {san}'
            if source == 'repertoire':
                note += f'\n\U0001F9EC {san} — his real move in this position.'
            else:
                feats = ', '.join(sorted(contribs, key=contribs.get,
                                         reverse=True)[:3]) if contribs else ''
                note += f'\n\U0001F9EC {san} — style pick' + \
                    (f' [{feats}]' if feats else '') + '.'
        else:
            score, nodes, level = info
            depth = engine.DIFFICULTY[level][0]
            # score is from the AI's perspective; negate for the human's view
            shown = -score / 100.0
            if abs(score) > engine.MATE - 1000:
                evaltxt = 'mate found'
            else:
                evaltxt = f'eval {shown:+.2f} (your perspective)'
            note = (f'\U0001F50D Engine search: {to_san(self.state, move)} — '
                    f'depth {depth}, {nodes:,} positions, {evaltxt}')
        self.apply_move(move, ai_note=note)

    def promotion_dialog(self, promo_moves):
        dlg = tk.Toplevel(self.root)
        dlg.title('Promote pawn')
        dlg.configure(bg=PANEL)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        tk.Label(dlg, text='Promote pawn to:', bg=PANEL, fg=FG,
                 font=('Segoe UI', 11, 'bold')).pack(padx=16, pady=(12, 6))
        row = tk.Frame(dlg, bg=PANEL)
        row.pack(padx=16, pady=(0, 14))
        for promo in ('Q', 'R', 'N', 'B'):
            m = next((x for x in promo_moves if x.promo == promo), None)
            if not m:
                continue
            pal = themes.APP_PALETTES[APP_MODE]
            promo_fg = pal['promo_white'] if self.human == 'w' else pal['promo_black']
            tk.Button(row, text=GLYPH[promo], font=('Segoe UI Symbol', 22),
                      width=3, bg=TEXTBG, fg=promo_fg,
                      relief='flat', cursor='hand2',
                      command=lambda mv=m: (dlg.destroy(), self.human_move(mv))
                      ).pack(side='left', padx=4)
        dlg.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dlg.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f'+{x}+{y}')

    # ------------------------------------------------------------- analysis
    def analyze_game(self):
        if self.ai_thinking or self.analyzing or not self.history:
            if not self.history:
                self.set_status('Nothing to analyze yet — play some moves first.')
            return
        self.analyzing = True
        self.set_status('Analyzing your game…', WARN)
        moves = [(h['move'], h['san']) for h in self.history]
        human = self.human

        def progress(i, total):
            self.root.after(0, lambda: self.set_status(
                f'Analyzing your game… move {i}/{total}', WARN))

        def worker():
            report = run_game_analysis(moves, human, self.kb, progress)
            self.root.after(0, lambda: self.show_analysis(report))

        threading.Thread(target=worker, daemon=True).start()

    def show_analysis(self, report):
        self.analyzing = False
        self.update_status()
        summary = report['summary']
        entries = report['entries']

        win = tk.Toplevel(self.root)
        win.title('Game analysis — your play')
        win.configure(bg=BG)
        win.geometry('700x720')

        ap = themes.analysis_palette(APP_MODE)
        kind_style = {
            'book':       ('\U0001F4D6 book',  ap['book']),
            'best':       ('✓ best',      ap['best']),
            'excellent':  ('✓ excellent', ap['excellent']),
            'good':       ('· good',      FG),
            'inaccuracy': ('?! inaccuracy',    ap['inaccuracy']),
            'mistake':    ('? mistake',        ap['mistake']),
            'blunder':    ('?? blunder',       ap['blunder']),
        }

        head = tk.Frame(win, bg=PANEL, padx=14, pady=10)
        head.pack(fill='x', padx=12, pady=(12, 6))
        tk.Label(head, text=f'Accuracy: {summary["accuracy"]:.1f}%',
                 bg=PANEL, fg=FG, font=('Segoe UI', 16, 'bold')).pack(anchor='w')
        counts = summary['counts']
        counts_txt = '   '.join(f'{kind_style[k][0]}: {counts[k]}'
                                for k in ('best', 'excellent', 'good', 'inaccuracy',
                                          'mistake', 'blunder', 'book') if counts[k])
        tk.Label(head, text=f'{summary["human_moves"]} moves analyzed   |   '
                            f'avg. loss {summary["avg_loss"]:.0f} centipawns',
                 bg=PANEL, fg=MUTED, font=('Segoe UI', 10)).pack(anchor='w')
        tk.Label(head, text=counts_txt, bg=PANEL, fg=MUTED,
                 font=('Segoe UI', 10)).pack(anchor='w')

        # evaluation graph (your perspective: above the line = better for you)
        graph = report['graph']
        gw, gh = 660, 130
        gc = tk.Canvas(win, width=gw, height=gh, bg=TEXTBG, highlightthickness=0)
        gc.pack(padx=12, pady=(0, 6))
        mid = gh / 2
        gc.create_line(0, mid, gw, mid,
                       fill=themes.APP_PALETTES[APP_MODE]['graph_axis'])
        gc.create_text(36, 12, text='your eval +', fill=MUTED, font=('Segoe UI', 8))
        if graph:
            step = gw / max(1, len(graph))
            pts = []
            for k, (_, cp) in enumerate(graph):
                x = step * (k + 0.5)
                y = mid - (max(-800, min(800, cp)) / 800) * (mid - 8)
                pts.append((x, y))
            for a, b in zip(pts, pts[1:]):
                gc.create_line(*a, *b, width=2,
                               fill=themes.APP_PALETTES[APP_MODE]['graph_line'])
            for (x, y), e in zip(pts, entries):
                color = kind_style[e['kind']][1]
                rad = 4 if e['kind'] in ('mistake', 'blunder') else 2
                gc.create_oval(x - rad, y - rad, x + rad, y + rad,
                               fill=color, outline='')

        body = tk.Frame(win, bg=BG)
        body.pack(fill='both', expand=True, padx=12, pady=(0, 12))
        scroll = tk.Scrollbar(body)
        scroll.pack(side='right', fill='y')
        text = tk.Text(body, bg=TEXTBG, fg=FG, font=('Segoe UI', 10), wrap='word',
                       relief='flat', padx=12, pady=10, yscrollcommand=scroll.set)
        text.pack(fill='both', expand=True)
        scroll.config(command=text.yview)

        for k, (_, color) in kind_style.items():
            text.tag_configure(k, foreground=color, font=('Segoe UI', 10, 'bold'))
        text.tag_configure('cmt', foreground=MUTED)
        text.tag_configure('hdr', foreground=FG, font=('Segoe UI', 12, 'bold'))
        text.tag_configure('tip', foreground=ap['tip'])

        text.insert('end', 'Move by move\n', 'hdr')
        for e in entries:
            tag_txt, _ = kind_style[e['kind']]
            ev = e['eval_after']
            ev_txt = ('#' if abs(ev) > 90000 else f'{ev / 100:+.1f}')
            text.insert('end', f'\n{e["label"]}  ')
            text.insert('end', f'{tag_txt}', e['kind'])
            text.insert('end', f'   [{ev_txt}]')
            if e['comment']:
                text.insert('end', f'\n    {e["comment"]}', 'cmt')
            text.insert('end', '\n')

        text.insert('end', '\n\nHow you should be playing\n', 'hdr')
        if summary['advice']:
            for tip in summary['advice']:
                text.insert('end', f'\n• {tip}\n', 'tip')
        else:
            text.insert('end', '\nNo specific advice — keep playing!\n', 'tip')
        text.configure(state='disabled')

    # ------------------------------------------------------------- controls
    def new_game(self):
        if self.analyzing:
            return
        self.state = State()
        self.history = []
        self.selected = -1
        self.targets = []
        self.ai_thinking = False
        self.game_over = False
        self.human = 'w' if self.side.get() == 'White' else 'b'
        self._last_ai_note = None
        self.clone_report_shown = False
        if self.clone_provider is not None:
            self.clone_provider.reset()      # clear per-game influence tally
        if self._opponent_is_clone():
            from player_clones.personality import SamayCommentator
            self.commentator = SamayCommentator(self.clone_mode_key)
            self._last_ai_note = '\U0001F3A4 ' + self.commentator.game_start()
        else:
            self.commentator = None
        self._update_opponent_ui()
        self.redraw()
        self.update_status()
        if self.state.turn != self.human:
            self.schedule_ai()

    def undo(self):
        if self.ai_thinking or self.analyzing or not self.history:
            return
        h = self.history.pop()
        unmake_move(self.state, h['move'], h['undo'])
        if self.history and self.state.turn != self.human:
            h = self.history.pop()
            unmake_move(self.state, h['move'], h['undo'])
        self.game_over = False
        self.selected = -1
        self.targets = []
        self.redraw()
        self.update_status()
        if self.state.turn != self.human and not self.game_over:
            self.schedule_ai()


if __name__ == '__main__':
    root = tk.Tk()
    app = ChessApp(root)
    root.mainloop()
