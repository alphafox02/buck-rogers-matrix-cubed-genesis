# The world, as the games actually play it

Walked in the DOS original with `tools/dosdrive` and read with
`tools/dosocr`; the Genesis column is `tools/tour.py` on the same script
block. Block numbers are DOS's; the port's area id is the hex spelling of
the same decimal number, so block 20 is area `0x14`.

## The spine

```
block 16   the briefing -- Buck sends the team to guard Lord Berkeley
block 17   Caloris dock, Mercury          -- walkable, 16x16
block 18   Salvation, NEO's headquarters   -- a menu hub, no map
block 19   interplanetary space            -- the ship, fuel, approaches
block 20   a spaceport                     -- Tycho, Hielo and others
```

## Caloris dock (17)

Gated on one counter, `[0x4C2C]`, and the order is not the obvious one:

```
Dr Romney            4,2    HELP ROMNEY                stage 0 -> 1
the tannoy          11,4                               sets [0x4C07] = 1
the courtesy console 11,5   bumped west from 12,5      clears it; de Sade
the coronation       2,12   the assassination          [0x4C2F] |= 8
SECURITY FORCES      5,10   QUESTION, never ATTACK     [0x4C2F] |= 2
the Terran leader    0,6    the fight                  stage -> 3
the ship             0,2    pushed west                NEW_ECL 18
```

The security forces can only be asked once. Their guard is
`([0x4C2F] & 3) == 0` and fighting them sets bit 1, so one wrong answer
removes the only line that sets bit 2 and the dock never lets go.

## Salvation (18)

```
WHERE DO YOU WISH TO GO?   BAR CLINIC DEPOT TRAINING PORT
  BAR       'THE LOST ORBIT' -- Salvation's port lounge
            BUY DRINKS TALK WAIT EXIT
  CLINIC    the autodoc heals everyone in the team
  DEPOT     BUY SELL AMMO VIEW POOL EXIT
  TRAINING  the roster, with TRAIN CHARACTER added
  PORT      LAUNCH REPAIR FUEL AMMO MED SUP EXIT
```

The port matches all of it. The one difference is at the spaceport, and it
is a single accommodation rather than two faults: the label set is 36
columns against the Genesis menu's 35, so `transpile.fit_labels` drops a
word from the longest label -- MED SUP becomes MED -- and `SELECT_ACTION`
goes out as `HMENU`, which buys eight columns by not printing "WHAT DO YOU
DO?" first.

## Space (19)

LAUNCH gives "ALL PREPARATIONS ARE COMPLETE. YOU ARE CLEARED FOR LAUNCH."
and then the solar system: the ship drifting among planets and asteroids,
`MOVE ROCKET CHANGE SAVE`, and a fuel counter falling ten at a time. Coming
near a body offers "MOVE INTO AN APPROACH PATTERN?" and then which port --
from Earth's neighbourhood, `SALVATION` or `TYCHO`.

Approaching runs SCANNING... CLOSING... LANDING..., and the docking is
scored: "YOU ARE JARRED AS T2 BACKS DOWN THE POWER A LITTLE TOO LATE."

## A spaceport (20) -- Tycho, on Luna

```
BANK DOWNTOWN HOSPITAL PORT TRAINING
  BANK      the main branch of the Bank of Luna
            DEPOSIT WITHDRAW TRANSFER EXIT
  DOWNTOWN  BAR LIBRARY RESTAURANT SHOP EXIT
    BAR         'JIMBO'S ROCKET BAR'      BUY DRINK TALK WAIT EXIT
    LIBRARY     "YOU SEARCH THE STACKS FOR ANY IMPORTANT INFORMATION" --
                and, this time, "YOU GET LOST AND WASTE THE AFTERNOON"
    RESTAURANT  'FREEFALL B+G.'           ORDER FOOD TALK WAIT EXIT
    SHOP        HIGGERT METALS / TECH / WEAPONS
  HOSPITAL  the Luna hospital             HEAL EXIT
  PORT      the main port area            LAUNCH REPAIR FUEL AMMO MED SUP
    REPAIR    ESTIMATE REPAIR DONE
    FUEL      capacity 45, 20 CR per unit
    AMMO      K-cannon reload 1500 CR, missile 300 CR
    MED SUP   2000 CR per unit
  TRAINING  the roster screen
```

Ship services bill the **NEO account** -- 20,000 CR -- not the party's own
credits, which is why a team carrying 1,000 apiece is told "YOU NEED MORE
MONEY" by the library and the hospital while happily refuelling.

One block serves every spaceport: DOS says "THE TYCHO SPACEPORT ON THE
SURFACE OF LUNA" and "the MAIN branch of the Bank of Luna" where the port,
arriving elsewhere, says "THE HIELO ORBITAL SPACESTATION OVER MERCURY" and
"the MERCURY branch". Same code, the names coming from variables the
arrival sets.

The port shows `BANK DOWNTOW HOSPITAL PORT TRAINING`, one character short.
That is `fit_labels` again: 36 columns against 35, and with no filler word
to drop and no multi-word label to shorten it falls through to its last
resort and clips the longest word.

## Ship-to-ship combat (in block 19)

Crossing the system runs into traffic: "SENSORS IDENTIFY A PIRATE MED.
CRUISER ON LR SCANNER. WHAT DO YOU DO? HAIL ATTACK FLEE". Hailing a pirate
opens the tactical screen -- the other ship drawn large, both ships'
systems, and a weapons rack.

```
                    FLARE (a pirate)   MAELSTROM RIDER (ours)
HULL                      400                600
SENSORS                   100                150
CONTROL                   100                150
LIFE                      200                300
FUEL                      300                320
ENGINE                    300                450
weapons                                      K-CANNON 2, MISSILE 2, LASER 5
```

It is crew-driven and turn-based. Each character is asked "WHAT DOES T2
WANT TO DO?" in turn; `QUIT` passes to the next one rather than leaving.
`COMMAND` puts a character at a station -- "T2 TAKES OVER AS PILOT" -- and
what the menu offers then depends on the range:

```
far        QUIT VIEW COMMAND
piloting   QUIT VIEW CLOSE WITHDRAW
in range   FIRE TARGET QUIT VIEW CLOSE WITHDRAW
close      FIRE TARGET QUIT VIEW WITHDRAW RAM
```

and the other ship plays the same game: "ENEMY SHIP ATTEMPTS TO RAM! TRY TO
DODGE ENEMY SHIP? YES NO".

Withdrawing is not immediate -- twenty rounds of it left the range at 8 and
the status still CLOSING -- so an encounter is a real engagement rather than
something to walk away from. It took about forty rounds of closing, firing
and dodging before the screen handed the party back to the star map.

This is the DOS side of the `SPACECOMBAT` opcode, 0x1F, which until now was
only a fetch count in the Genesis handler table.
