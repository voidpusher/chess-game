"""Samay essence layer — live, mode-aware stream banter.

The clone already *moves* like Samay; this makes it *feel* like him. A
`SamayCommentator` watches what actually happens on the board (his sacrifices,
checks, book moves, your blunders, the eval swinging) and reacts the way a
chess streamer would — Hinglish, hyped, a little merciless.

All lines are original, written to evoke the chess-stream vibe rather than
quote anyone. Event detection is driven by data the clone engine already
produces (decision source, style contributions, candidate evals) — no new chess
logic lives here.

Mode flavour:
    casual   -> maximum masti, louder, more taunts
    real     -> the standard stream mix
    peak     -> locked in: shorter, colder, focused
    adaptive -> encouraging, coach-like warmth mixed in
"""

from __future__ import annotations

import random
from typing import Optional

# --------------------------------------------------------------------------- #
# Line pools (event -> lines). {san} is substituted where present.
# --------------------------------------------------------------------------- #

LINES = {
    "start": [
        "Chaliye shuru karte hain! Board set, chai ready. Best of luck — you'll need it. ♟️",
        "Aaj ka stream sponsored by: your upcoming blunders. Let's go!",
        "Theek hai theek hai, ek game ho jaaye. Main full form mein hoon aaj.",
        "Welcome welcome! Seedha game khelte hain, no warm-up, full confidence.",
        "CHAT! Hum aa gaye! Ek game khelte hain, National Master ka level dikhata hoon. 😎",
        "Namaste doston! Aaj King's Gambit khelunga, kya karu — King's Gambit mera pyaar hai.",
        "Magnus banne ka sapna lekar baitha hoon, tum bas mohra ho is journey mein. Chalo!",
        "Arre yaar game start karein? Main 1500 ELO hoon par confidence 2700 ka hai.",
        "Theek hai bhai, pehla move tera. Main dekh raha hoon, calculation chal rahi hai.",
        "Chess is chess. Jo hona hai hoga. Par main full attack mode mein hoon, bata diya.",
        "Setup ready, ab dekho asli chess. Nihal ke saath practice kiya hai maine, samajh le.",
        "Ek baat bol du — sacrifice aayega aaj. Pakka. Likh ke rakh lo chat.",
    ],
    "start_casual": [
        "Casual game hai bhai, masti karenge. Sacrifice pakka aayega, likh ke lo!",
        "Aaj accuracy ki tension nahi — sirf content. Chess but make it entertainment!",
        "Arre yaar fun game hai, blunder bhi karunga toh hasenge saath mein. Chalo!",
        "Casual matlab full masti. Aaj pieces aise gift karunga jaise Diwali ho. 🎁",
        "Tension nahi lene ka. Haar gaya toh bolunga 'chess is chess' aur agla game.",
    ],
    "start_peak": [
        "Locked in. No jokes today. Sirf chess.",
        "Headphones on, chat off. Aaj serious wala Samay mil raha hai tumhe.",
        "Aaj National Master ka asli matlab dikhata hoon. Focus mode.",
        "Calculation deep ja rahi hai aaj. Ek bhi blunder nahi. Dekhte rehna.",
    ],
    "start_adaptive": [
        "Tere level pe khelta hoon aaj — fair game, full respect. Dikha kya seekha hai!",
        "Coach mode on. Achha khelega toh main bhi seriously khelunga. Deal?",
        "Aaj sikhata hoon thoda. Galti karega toh batata jaunga, theek hai dost?",
        "Relax karke khel. Main tujhe push karunga par girne nahi dunga. Chal shuru.",
    ],
    "repertoire": [
        "{san} — ye line maine hazaar baar kheli hai. Muscle memory, baby!",
        "{san}. Iss position mein main hamesha yahi khelta hoon. Home ground hai ye.",
        "Book move {san} — tu meri prep mein ghus gaya hai, ab bhugat.",
        "{san}, classic. Mere games dekhe hote toh pata hota ye aane wala tha.",
        "{san}! Ye toh meri bread and butter hai bhai. Aankh band karke khel sakta hoon.",
        "{san} — Nihal ne sikhaya tha ye line. Theory clear hai mera.",
        "Dekh {san}. Main itni baar ye position pe aaya hoon ki ghar lagti hai.",
        "{san}, prep ka part. Tu jo bhi khelega, mere paas jawaab ready hai.",
        "{san} — yahi toh khelte hain is opening mein. Mainline, no shortcut.",
        "Arre {san}, ye line pyaari hai mujhe. King's Gambit ho ya Italian, repertoire solid hai.",
    ],
    "sacrifice": [
        "SACRIFICE!! {san}!! Clip it, clip it, CLIP IT! 🔥",
        "{san} — piece gaya? Gaya. Tension hai? Bilkul nahi. Compensation dekh.",
        "Le {san}! Material toh sirf number hai bhai, initiative asli paisa hai.",
        "{san}!! Haan haan, le le piece. Teri king ki taraf aa raha hoon main.",
        "OHH! OHH! Wait wait wait... {san}!! Ye sacrifice banta hai chat!",
        "{san} — piece de diya, izzat nahi. Attack ke saamne material kuch nahi hai.",
        "Material down? {san} ke baad mujhe farak nahi padta. Tabiyat khush ho gayi.",
        "{san}!! Tal hota toh proud hota mujhpe. Sacrifice mera pehla pyaar hai. 🔥",
        "Le piece, le. {san}. Main toh attack khelne aaya hoon, counting baad mein.",
        "{san} — arre ye sirf sacrifice nahi, statement hai. CHAT DID YOU SEE THAT??",
        "Bhai {san}! Engine ro raha hoga par dil keh raha hai 'khel de'. Khel diya.",
        "{san}!! Risk hai? Haan. Worth it? Bilkul. Main aise hi khelta hoon yaar.",
    ],
    "check": [
        "{san} — CHECK! Raja ji ko thoda exercise karwate hain.",
        "Check de diya {san}. King ko ghar se nikaalo, dar lag raha hoga.",
        "{san}+ — ab bhaag raja, bhaag!",
        "{san}! Check. Teri king ke peeche pad gaya hoon, ab chain se nahi baithne dunga.",
        "Arre {san}+ — raja ko hawa khilane le ja raha hoon. Walk karo majesty.",
        "{san}. King exposed, ab attack ka mazaa aayega. Dekhte raho.",
        "{san}+! Chhoti si check, badi si tension teri taraf.",
    ],
    "mate": [
        "{san}#. CHECKMATE. GG bhai, stream pe aane ke liye shukriya. 🎤⬇️",
        "Aur bas. {san} — mate. Chess is chess, kuch nahi kar sakte.",
        "{san}#!! GG bhai! National Master ne kaam kar diya. Clip ready chat?",
        "Checkmate {san}#. Bola tha na sacrifice ke baad mate aayega? Aaya. 😎",
        "{san}# — aur game khatam. Magnus dekh raha hoga kahin se, proud hoga.",
        "Bas ho gaya. {san}#. GG bhai, achha khela tune par mate toh mate hai.",
        "{san}#! CHAT WE DID IT! King hunt successful. Ye wala frame karke rakhna.",
    ],
    "big_capture": [
        "{san} — bada wala piece utha liya. Dhanyavaad, bahut kripa.",
        "Free real estate! {san}, ye toh gift tha bhai.",
        "{san}. Itna mehenga piece aise nahi chhodte yaar, dil dukhta hai.",
        "{san}! Le liya. Material ab mere paas, attack bhi mere paas. Double profit.",
        "Thank you, thank you. {san} — itni badi cheez free mein? Main mana nahi karta.",
        "{san}. Piece gaya tera, gaya. Ab game ka rukh dekh.",
    ],
    "castle": [
        "{san} — raja safe, ab attack ki taiyari. Pehle ghar, phir jung.",
        "Castle kar liya {san}. Insurance ho gaya, ab masti shuru.",
        "{san}. Haan kabhi kabhi castle bhi kar leta hoon, surprise! Ab attack pakka.",
        "{san} — king ko ghar bhej diya. Ab front pe sirf attack ki baat hogi.",
    ],
    "king_attack": [
        "{san} — teri king ke mohalle mein aa gaya hoon. Padosi ban gaya samajh.",
        "Pieces saari teri king ki taraf ja rahi hain {san}. Coincidence? Nahi.",
        "{san}! King hunt shuru. Teri raja ki neend udd jayegi ab.",
        "{san} — saara army teri king pe. Defence dhoondh, time nahi milega zyada.",
        "Dekh {san}. Ek ek piece teri king ke ghar ki taraf march kar raha hai.",
    ],
    "user_blunder": [
        "Arre arre arre... ye kya tha?! {san} — main toh bas shukriya bolunga.",
        "Bhai. BHAI. Wo piece wapas nahi milega. {san}, dhanyavaad. 😂",
        "Chat, did you see that?? Okay okay, composure. {san}. Hehe.",
        "Ye move dekh ke mere andar ka content creator khush ho gaya. {san}!",
        "OHH! Tune ye khel diya?! {san} — bhai sambhal ke, main free mein le raha hoon.",
        "Arre yaar {san} — ye toh maine bhi nahi socha tha. Tera gift accept karta hoon.",
        "CHAT! CHAT! Dekha?? {san}. Main kuch nahi bolunga, position khud bol rahi hai. 😂",
        "{san} — uff. Itni badi galti? Koi nahi, main capitalize karta hoon turant.",
        "Haaye {san}! Tune toh apna piece haath mein rakh ke de diya. Dhanyavaad bhai.",
    ],
    "clone_worse": [
        "Hmm {san}... thoda pressure hai, manta hoon. Comeback dekhna bas.",
        "Achha khel raha hai tu, sach mein. {san} — par game abhi baaki hai mere dost.",
        "Okay okay, respect. {san}. Ab main serious ho raha hoon.",
        "{san}. Position kharab hai, accept karta hoon. Par main haar nahi maanta jaldi.",
        "Thoda phasa hoon {san}... par chess is chess, ek tactic mili toh palat dunga.",
        "Arre {san} — tu sach mein achha khel raha hai. Vidit level ka move tha wo.",
        "{san}. Defence mode on. Ek chance milega, main use karunga. Dekhte raho.",
    ],
    "quiet": [
        "{san}. Solid, positional, boring — sab plan ka hissa hai.",
        "{san} khelte hain, dekhte hain tu kya karta hai.",
        "Thoda sa {san}, thoda sa patience. Chess subtle game hai bhai.",
        "{san}. Centre control le raha hoon, dheere dheere ghutan hogi tujhe.",
        "{san} — develop kar raha hoon shaant se. Toofan se pehle ki khamoshi hai ye.",
        "{san}. Abhi quiet hai, par attack ki taiyari andar andar chal rahi hai.",
        "{san} khela. Position build kar raha hoon, phir ek dum se phategi.",
        "{san} — patience yaar. Sabar ka phal sacrifice hota hai. Wait karo.",
    ],
    "win": [
        "GG! Mazaa aaya. Rematch? Is baar tu white le lena, handicap ke saath bhi jeet jaunga. 😎",
        "Aur ye raha result! Chess is chess. Subscribe... matlab, New Game daba.",
        "GG bhai! Bola tha na National Master se panga mehenga padega. 🎤",
        "Jeet gaye! Magnus, dekh raha hai na? Ye tera competition aa raha hai. 😂",
        "GG! Achha khela tune par aaj mera din tha. Rematch ka mann hai? Aaja.",
        "Aur khatam! Sacrifice kaam aaya. CHAT clip kar liya na wo move?",
        "GG bhai, shukriya game ke liye. Chess is chess, aaj jeet meri.",
    ],
    "loss": [
        "Haan bhai haan, jeet gaya tu. Screenshot le le, dobara nahi hoga. GG! 🤝",
        "Tune mujhe hara diya?? Respect. Ab rematch — izzat ka sawaal hai.",
        "Chess is chess yaar. Haar gaya. Wo sacrifice nahi khelna chahiye tha. GG bhai.",
        "Arre haar gaya main?! 1500 ELO hoon na, kya karoon. 😅 GG, achha khela tu.",
        "GG. Ye move nahi khelnaa chahiye tha mujhe, par chalो — seekhte hain. Rematch?",
        "Bhai jeet gaya tu, mann se. Main over-sacrifice kar gaya, aadat hai. GG! 🤝",
        "Haar bhi content hai. GG bhai, izzat se haara hoon. Ab rematch, izzat wapas chahiye.",
    ],
    "draw": [
        "Draw?! Itna lamba khel ke draw?? Theek hai, dono ka rating bach gaya.",
        "Draw ho gaya. Boring but fair. Agli baar decisive hoga, promise.",
        "Draw?! Yaar main attacker hoon, draw mere DNA mein nahi hai. Par theek hai. 🤝",
        "Half-half. GG bhai. Agli baar King's Gambit khelunga, draw nahi hone dunga.",
    ],
    # New analysis / situational events
    "opening_theory": [
        "{san} — pure theory bhai. Ye line maine YouTube pe bhi explain ki hai.",
        "{san}. Book move, mainline. Yahin se game ka character banta hai.",
        "Dekho {san} — ye opening ka soul hai. Yahi khelna chahiye is position mein.",
        "{san}, theory ke according. Galat khelta toh Vidit daant deta. 😂",
        "{san} — opening prep solid hai mera. Nihal ke saath ye sab dekha hai.",
        "Classic {san}. Is opening mein agar ye nahi khela toh kya hi khela.",
    ],
    "missed_tactic": [
        "Ruko... {san} better tha yahaan. Maine miss kar diya. Insaan hoon yaar.",
        "Analysis mein dekho — {san} khelna chahiye tha. Galti se learning.",
        "Arre {san} tha na! Stream pe pressure mein dimaag ne dhoka de diya.",
        "Ye move nahi khelnaa chahiye tha, {san} sahi tha. Chess is chess, aage badho.",
        "Engine bolega {san}. Main bola 'attack', engine bola 'calculate'. 😂 Next time.",
    ],
    "time_pressure": [
        "Time kam hai! Pre-move, pre-move — {san}! Sochne ka time nahi.",
        "Clock down bhai. {san} khel diya, intuition pe bharosa. Bullet hai ye.",
        "Arre time! {san} — flag girne se pehle move karna hai. Speed chess baby!",
        "Seconds bache hain, {san} maar diya. Calculation? Kaun karta hai itne time mein.",
        "Low time! {san}. Ab sirf instinct, dimaag baad mein. CHAT pray karo!",
    ],
    "pawn_push": [
        "{san} — pawn aage! Storm aa raha hai teri king ki taraf.",
        "Push {san}! Pawns bhi soldier hote hain, attack mein bhej diya.",
        "{san} — ye pawn rukega nahi. Promotion tak ka plan hai mera.",
        "Aage badho! {san}. Pawn push se hi toh space milta hai attack ke liye.",
        "{san} — chhota pawn, bada irada. Teri position phaadne aaya hai ye.",
    ],
}

# Mode-specific extra spice appended to the relevant pools.
_MODE_EXTRA = {
    "casual": {
        "sacrifice": ["{san}!! Kyun? KYUNKI MAZAA AATA HAI! Yahi toh content hai!",
                      "{san}!! Piece? Le le bhai, casual hai. Mauj karenge!"],
        "quiet": ["{san}... boring move maaf karna, agla wala spicy hoga pakka."],
        "user_blunder": ["HAHAHA {san} — bhai tu bhi casual mood mein hai kya?!"],
        "pawn_push": ["{san}! Pawn bhej diya masti mein. Dekhte hain kya hota hai. 😄"],
        "time_pressure": ["{san}! Time kam, masti zyada. Pre-move chaalu!"],
    },
    "peak": {
        "repertoire": ["{san}. Prep."],
        "quiet": ["{san}. Best move tha, isliye khela.", "{san}. Calculate karke aaya hoon."],
        "sacrifice": ["{san}. Ye sacrifice nahi, calculation hai."],
        "check": ["{san}+. Forced sequence shuru."],
        "opening_theory": ["{san}. Theory. Next."],
        "missed_tactic": ["{san} tha. Noted. Aage."],
        "pawn_push": ["{san}. Space. Plan ka hissa."],
    },
    "adaptive": {
        "user_blunder": ["{san} — koi nahi, sabse seekha jaata hai. Agli baar wo piece dekh ke chalna."],
        "clone_worse": ["Bahut badhiya khel raha hai! {san} — ab dikha consistency."],
        "missed_tactic": ["Dekh, {san} behtar tha — dono ke liye learning hai ye."],
        "opening_theory": ["{san} — ye theory yaad rakhna, kaam aayegi tere games mein."],
    },
}


def _is_pawn_push(san: str) -> bool:
    """True if `san` looks like a non-capturing pawn advance (e.g. e4, d5, h4).

    Pawn moves have no leading piece letter; captures contain 'x'; castling
    starts with 'O'. We treat a plain file+rank token as a pawn push.
    """
    if not san:
        return False
    if san[0] in "KQRBNO" or "x" in san:
        return False
    head = san.rstrip("+#")
    return len(head) >= 2 and head[0] in "abcdefgh" and head[1].isdigit()


class SamayCommentator:
    """Per-game banter engine. Create one per game (cheap), feed it events."""

    def __init__(self, mode_key: str = "real", rng: Optional[random.Random] = None):
        self.mode = mode_key
        self.rng = rng or random.Random()
        self._recent: list[str] = []          # avoid repeating lines back-to-back
        self._prev_eval: Optional[int] = None # clone's eval after its last move

    # ------------------------------------------------------------- events #
    def game_start(self) -> str:
        pool = list(LINES["start"])
        keyed = LINES.get(f"start_{self.mode}")
        if keyed:
            pool = keyed + pool               # mode greeting takes priority
        return self._pick(pool)

    def on_clone_move(self, san: str, source: str, contributions: dict,
                      eval_cp: Optional[int]) -> str:
        """Banter for the clone's move, chosen by what the move actually was."""
        c = contributions or {}
        event = "quiet"
        if "mate" in c:
            event = "mate"
        elif "sacrifice" in c and c["sacrifice"] > 0:
            event = "sacrifice"
        elif eval_cp is not None and self._prev_eval is not None \
                and eval_cp - self._prev_eval >= 180:
            event = "user_blunder"            # eval jumped our way: you helped
        elif "check" in c:
            event = "check"
        elif c.get("capture", 0) >= 0.25:
            event = "big_capture"
        elif source == "repertoire":
            event = "repertoire"
        elif eval_cp is not None and eval_cp <= -120:
            event = "clone_worse"
        elif "castle" in c:
            event = "castle"
        elif "king_attack" in c:
            event = "king_attack"
        elif _is_pawn_push(san):
            event = "pawn_push"

        if eval_cp is not None:
            self._prev_eval = eval_cp
        return self._line(event, san)

    def on_game_over(self, clone_won: Optional[bool]) -> str:
        if clone_won is None:
            return self._line("draw", "")
        return self._line("win" if clone_won else "loss", "")

    def on_opening_theory(self, san: str = "") -> str:
        """Commentary when a known book/theory line is being followed."""
        return self._line("opening_theory", san)

    def on_missed_tactic(self, better_san: str = "") -> str:
        """Post-game analysis line: a stronger move was available."""
        return self._line("missed_tactic", better_san)

    def on_time_pressure(self, san: str = "") -> str:
        """Low-clock commentary (bullet/blitz scrambles)."""
        return self._line("time_pressure", san)

    # ------------------------------------------------------------ internal #
    def _line(self, event: str, san: str) -> str:
        pool = list(LINES.get(event, LINES["quiet"]))
        pool += _MODE_EXTRA.get(self.mode, {}).get(event, [])
        return self._pick(pool).replace("{san}", san)

    def _pick(self, pool: list[str]) -> str:
        fresh = [p for p in pool if p not in self._recent] or pool
        choice = self.rng.choice(fresh)
        self._recent.append(choice)
        if len(self._recent) > 6:
            self._recent.pop(0)
        return choice
