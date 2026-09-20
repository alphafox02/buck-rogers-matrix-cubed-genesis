# Every area in the port, and what it says

Built by `tools/tour.py`, which boots straight into an area with
`tools/visit.py`, reads the screen off the tilemap (`tools/genread.py`) and
answers each prompt the way a cautious player would -- EXIT, NO, LEAVE --
so a sweep does not buy drinks in every bar it finds. "Leads to" is the
DOS script's own `NEW_ECL`, read by `tools/levelmap.py`.

Area ids are the hex spelling of the DOS block's decimal number, which is
what `tools/build.py` transplants them as: DOS block 18 becomes area `0x12`,
block 112 becomes `0x70`.

| area | from | leads to | what it says when you walk in |
|------|------|----------|-------------------------------|
| `0x02` | block 2 | 1 | *nothing yet* |
| `0x10` | block 16 | 19 | APPEARS ONSCREEN. 'BERKELEY IS CALLING FOR A |
| `0x11` | block 17 | 18 | *nothing yet* |
| `0x12` | block 18 | 19 | BUCK IS WAITING FOR YOU. 'GOOD JOB, TEAM. A LITTLE OF LORD BERKELEY'S |
| `0x13` | block 19 | 17, 18, 20, 21, 32, 35, 48, 64, 82, 97 | APPEARS ONSCREEN. 'I KNOW YOU'RE ITCHING TO PULL MORE |
| `0x14` | block 20 | 95 | YOU ARE AT THE MERCURY BRANCH OF THE BANK OF LUNA. |
| `0x15` | block 21 | 19 | YOU CHARGE THROUGH THE BOARDING TUBE AND ATTACK! |
| `0x18` | block 24 | - | THIS ADVENTURE TAKES YOU TO THE FURTHEST REACHES OF CIVILIZED SPACE |
| `0x20` | block 32 | 19, 33, 34, 38, 81 | YOU LAND AT DUKE'S HILL SPACEPORT IN LOSANGELORG. |
| `0x21` | block 33 | 32, 37 | THE RUBBLE. YOU RECOIL AT THE STENCH OF DEPRIVATION AND DEATH. |
| `0x22` | block 34 | 32, 36 | YOU ENTER THE FRONT LOBBY OF THE HISTORICAL MUSEUM. DUST COVERS |
| `0x23` | block 35 | 19 | AS OVERDUE FOR MAINTENANCE.' 'CONFERENCE ROOM.' |
| `0x24` | block 36 | - | THE MATTRESS SMELLS OF PERFUME. TEAM FAILS AT PERCEPTION |
| `0x25` | block 37 | 33 | THEY ATTACK!APES MOVE OUT OF THE THEY ATTACK!APES MOVE OUT OF THE |
| `0x26` | block 38 | 32 | YOU DON'T HAVE A BOAT! |
| `0x30` | block 48 | - | CLOUDS, THICK WITH ACID, BOIL OVERHEAD. 'YOU'D BETTER HURRY TO THE LOWLANDER VILLAGE!' |
| `0x31` | block 49 | - | SEEMS RECENTLY ABANDONED. OF THE LOWLANDER VILLAGE. YOU SEE A SMALL |
| `0x32` | block 50 | 48, 49 | ENTERING THE LAB COMPLEX, YOU FIND THE SOURCE OF THE EARTHQUAKE. AN |
| `0x34` | Countdown | - | *not replaced* |
| `0x40` | block 64 | - | A SIGN ABOVE THE DOOR READS: 'SENATOR KOI POLITICAL OFFICE' |
| `0x41` | block 65 | - | AS YOU ENTER THE MAIN RESEARCH SECTION, YOU SEE A PARTIALLY |
| `0x42` | block 66 | 80 | YOUR DEPARTURE FROM LUNA GOES SMOOTHLY. |
| `0x43` | Countdown | - | *not replaced* |
| `0x50` | block 80 | 18 | YOU WAKE SLOWLY. |
| `0x51` | block 81 | 32 | YOU ENTER THE LOBBY OF PURGE HEADQUARTERS. |
| `0x52` | block 82 | 19 | A TALL MAN MEETS YOU. 'I'M FREDRICKSON, THE DIRECTOR. SEARCH |
| `0x53` | Countdown | - | *not replaced* |
| `0x54` | block 84 | 81 | - GROUND FLOOR - - GROUND FLOOR - |
| `0x5E` | Countdown | - | *not replaced* |
| `0x5F` | block 95 | 19, 20 | YOU ARE AT THE HIELO ORBITAL SPACESTATION OVER MERCURY. |
| `0x60` | block 96 | 97, 112 | PIRATES PATROL THE AREA. WHAT DO YOU DO? ATTACK HIDE MOVE AWAY |
| `0x61` | block 97 | 19, 96, 98, 112 | PIRATES COME INTO VIEW. WHAT DO YOU DO? ATTACK HIDE MOVE AWAY |
| `0x62` | block 98 | 97, 112 | THE ROBOTS DEMAND TO SEE YOUR PASS. WHAT DO YOU DO? |
| `0x63` | Countdown | - | *not replaced* |
| `0x70` | block 112 | 113, 114 | A STORMRIDER APPROACHES. 'I AM DR. MAKALI'S ASSISTANT. SHE IS EXPECTIN |
| `0x71` | block 113 | 112 | 'THERE IT IS, NEO AGENTS, GENETICS FOUNDATION--THE HOME OF OUR SLAVE |
| `0x72` | block 114 | - | A ROBOT MEETS YOU. 'GREETINGS. DR. MAKALI, COME WITH ME. TEAM, PLEASE |

## Seven areas are still Countdown's

`0x01`, `0x03`, `0x34`, `0x43`, `0x53`, `0x5E` and `0x63` carry Countdown's
own text pool, byte for byte -- Matrix Cubed has 33 script blocks against
Countdown's 27 and the ids do not line up, so these were never overwritten.
They are dead weight rather than a bug while nothing reaches them, but they
are not inert: touring `0x5E` ended the party in `0x22`, so Countdown's
scripts can still hand the player to a Matrix Cubed area in the middle of a
scene. Anything that reaches one of them is a transplant fault.

## What the sweep found

The opening runs 16 -> 17 -> 18: the briefing, the Caloris dock, and
Salvation, where Buck takes Romney's notes and sends the team to the old RAM
base near Ceres. From 19, Salvation's star map, the game opens out to ten
destinations, and the areas behind them all introduce themselves correctly
in the port -- Duke's Hill spaceport in Losangelorg, the Sprawls, the
Historical Museum and its gift shop, the Mercury branch of the Bank of Luna,
Purge headquarters, the Hielo orbital station, the Venusian lab complex,
Dr Makali's Genetics Foundation.

Two areas still say nothing. `0x11` is the dock, and it is silent because
`visit.py` hijacks its init to get anywhere at all. `0x02` is DOS block 2,
the developer screen that asks you to "GIVE ALL NUMBERS IN DECIMAL"; it
draws nothing without being driven, which is what it should do.

`0x60` and `0x61` were silent at first for a different reason: the tour had
no cautious answer to "PIRATES PATROL THE AREA. WHAT DO YOU DO? ATTACK HIDE
MOVE AWAY", so it attacked, and the rest of the tour was a fight. HIDE,
MOVE AWAY, FLEE and WAIT are in the decline list now.
