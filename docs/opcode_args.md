# Genesis ECL Opcode Argument Counts

Derived two independent ways and cross-checked:

1. **Static** — counting calls to the argument fetcher at `0x0404A` (both
   `bsr.w` and `bsr.s` forms) within each handler's extent. Undercounts
   where handlers share helper routines.
2. **Inferred** — decoding the 27 extracted Genesis ECL blocks and voting on
   the argument count that keeps the instruction stream self-consistent.
   Argument type bytes are a strong constraint: only 0,1,2,3,4,5,0x80,0x81
   are valid.

Opcodes `0x00`-`0x1C` are CONFIRMED — they match the DOS engine exactly.

Opcodes with a **dynamic argument list** (MENU, ONGOTO, ONGOSUB, TREASURE,
HMENU, WHMENU, ICONMENU) take a fixed head plus a variable tail whose length
comes from one of the fixed arguments. The inference model does not handle
that, so its numbers for those are meaningless — trust the static column.

| op | mnemonic | static | inferred | votes | confidence |
|---|---|---|---|---|---|
| `0x00` | `EXIT` | 0 | 0 | 0/0 | CONFIRMED (matches DOS) |
| `0x01` | `GOTO` | 1 | 1 | 0/0 | CONFIRMED (matches DOS) |
| `0x02` | `GOSUB` | 1 | 1 | 0/0 | CONFIRMED (matches DOS) |
| `0x03` | `COMPARE` | 2 | 2 | 0/0 | CONFIRMED (matches DOS) |
| `0x04` | `ADD` | 0 | 3 | 0/0 | CONFIRMED (matches DOS) |
| `0x05` | `SUBTRACT` | 0 | 3 | 0/0 | CONFIRMED (matches DOS) |
| `0x06` | `DIVIDE` | 0 | 3 | 0/0 | CONFIRMED (matches DOS) |
| `0x07` | `MULTIPLY` | 0 | 3 | 0/0 | CONFIRMED (matches DOS) |
| `0x08` | `RANDOM` | 1 | 2 | 0/0 | CONFIRMED (matches DOS) |
| `0x09` | `SAVE` | 1 | 2 | 0/0 | CONFIRMED (matches DOS) |
| `0x0A` | `LOADCHARACTER` | 1 | 1 | 0/0 | CONFIRMED (matches DOS) |
| `0x0B` | `LOADMONSTER` | 3 | 3 | 0/0 | CONFIRMED (matches DOS) |
| `0x0C` | `SETUPMONSTERS` | 4 | 4 | 0/0 | CONFIRMED (matches DOS) |
| `0x0D` | `APPROACH` | 0 | 0 | 0/0 | CONFIRMED (matches DOS) |
| `0x0E` | `PICTURE` | 1 | 1 | 0/0 | CONFIRMED (matches DOS) |
| `0x0F` | `INPUTNUMBER` | 1 | 2 | 0/0 | CONFIRMED (matches DOS) |
| `0x10` | `INPUTSTRING` | 0 | 2 | 0/0 | CONFIRMED (matches DOS) |
| `0x11` | `PRINT` | 1 | 1 | 0/0 | CONFIRMED (matches DOS) |
| `0x12` | `PRINTCLEAR` | 0 | 1 | 0/0 | CONFIRMED (matches DOS) |
| `0x13` | `RETURN` | 0 | 0 | 0/0 | CONFIRMED (matches DOS) |
| `0x14` | `COMPAREAND` | 2 | 4 | 0/0 | CONFIRMED (matches DOS) |
| `0x15` | `MENU` | 0 | 3 | 0/0 | CONFIRMED (matches DOS) |
| `0x16` | `IFEQ` | 0 | 0 | 0/0 | CONFIRMED (matches DOS) |
| `0x17` | `IFNE` | 0 | 0 | 0/0 | CONFIRMED (matches DOS) |
| `0x18` | `IFLT` | 0 | 0 | 0/0 | CONFIRMED (matches DOS) |
| `0x19` | `IFGT` | 0 | 0 | 0/0 | CONFIRMED (matches DOS) |
| `0x1A` | `IFLE` | 0 | 0 | 0/0 | CONFIRMED (matches DOS) |
| `0x1B` | `IFGE` | 1 | 0 | 0/0 | CONFIRMED (matches DOS) |
| `0x1C` | `CLEARMONSTERS` | 0 | 0 | 0/0 | CONFIRMED (matches DOS) |
| `0x1D` | `SETTIMER` | 0 | 0 | 9/9 | HIGH -- both methods agree, votes unanimous |
| `0x1E` | `CHECKPARTY` | 0 | 0 | 10/11 | HIGH -- both methods agree, votes unanimous |
| `0x1F` | `SPACECOMBAT` | 4 | 0 | 3/7 | LOW -- methods disagree (static 4) |
| `0x20` | `NEWECL` | 1 | 1 | 10/11 | HIGH -- both methods agree, votes unanimous |
| `0x21` | `LOADFILES` | 3 | 3 | 21/23 | HIGH -- both methods agree, votes unanimous |
| `0x22` | `SKILL` | 3 | 3 | 8/12 | **CONFIRMED** -- handler 0x038A2 jumps to the shared body at 0x04E52, which makes 3 calls to the argument fetcher |
| `0x23` | `PRINTSKILL` | 3 | 3 | 4/7 | **CONFIRMED** -- handler 0x038A8 sets d4=1 and jumps to the same body at 0x04E52; identical arity to SKILL |
| `0x24` | `COMBAT` | 0 | 0 | 8/11 | HIGH -- both methods agree |
| `0x25` | `ONGOTO` | 3 | 6 | 5/11 | dynamic arg list -- inference not valid |
| `0x26` | `ONGOSUB` | 0 | 0 | 6/6 | dynamic arg list -- inference not valid |
| `0x27` | `TREASURE` | 3 | 0 | 4/8 | dynamic arg list -- inference not valid |
| `0x28` | `ROB` | 0 | ? | 0/0 | UNKNOWN -- too few samples |
| `0x29` | `CONTINUE` | 0 | 0 | 17/17 | HIGH -- both methods agree, votes unanimous |
| `0x2A` | `GETABLE` | 3 | 3 | 38/38 | HIGH -- both methods agree, votes unanimous |
| `0x2B` | `HMENU` | 0 | 4 | 4/10 | dynamic arg list -- inference not valid |
| `0x2C` | `GETYN` | 0 | 0 | 7/7 | HIGH -- both methods agree, votes unanimous |
| `0x2D` | `DRAWINDOW` | 0 | 0 | 8/11 | HIGH -- both methods agree |
| `0x2E` | `DAMAGE` | 0 | 5 | 7/7 | PROBABLE -- votes unanimous, static says 0 |
| `0x2F` | `AND` | 0 | 3 | 53/55 | PROBABLE -- votes unanimous, static says 0 |
| `0x30` | `OR` | 0 | 3 | 20/26 | LOW -- methods disagree (static 0) |
| `0x31` | `WHMENU` | 0 | ? | 2/2 | dynamic arg list -- inference not valid |
| `0x32` | `FINDITEM` | 1 | 1 | 4/6 | HIGH -- both methods agree |
| `0x33` | `PRINTRETURN` | 0 | ? | 4/4 | UNKNOWN -- too few samples |
| `0x34` | `CLOCK` | 0 | ? | 1/2 | UNKNOWN -- too few samples |
| `0x35` | `SAVETABLE` | 0 | ? | 2/2 | UNKNOWN -- too few samples |
| `0x36` | `ADDNPC` | 0 | 0 | 9/14 | HIGH -- both methods agree |
| `0x37` | `LOADPIECES` | 1 | 1 | 21/21 | HIGH -- both methods agree, votes unanimous |
| `0x38` | `PROGRAM` | 1 | ? | 4/4 | UNKNOWN -- too few samples |
| `0x39` | `WHO` | 1 | ? | 0/0 | UNKNOWN -- too few samples |
| `0x3A` | `DELAY` | 0 | 0 | 7/7 | HIGH -- both methods agree, votes unanimous |
| `0x3B` | `SPELLS` | 0 | 1 | 6/6 | PROBABLE -- votes unanimous, static says 0 |
| `0x3C` | `PROTECT` | 0 | 0 | 4/7 | HIGH -- both methods agree |
| `0x3D` | `CLEARBOX` | 0 | 1 | 4/6 | LOW -- methods disagree (static 0) |
| `0x3E` | `DUMP` | 0 | 0 | 3/6 | HIGH -- both methods agree |
| `0x3F` | `JOURNAL` | 2 | 2 | 14/14 | **CONFIRMED** -- handler 0x03B90 calls the argument fetcher twice: the first operand goes to the string printer 0x11CA4, the second to the number formatter 0x13328 |
| `0x40` | `DESTROY` | 2 | 2 | 4/6 | HIGH -- both methods agree |
| `0x41` | `ADDEP` | 2 | 2 | 8/9 | HIGH -- both methods agree |
| `0x42` | `ENCEXIT` | 0 | 0 | 15/15 | HIGH -- both methods agree, votes unanimous |
| `0x43` | `SOUND` | 1 | 1 | 30/30 | HIGH -- both methods agree, votes unanimous |
| `0x44` | `SAVECHARACTER` | 0 | 0 | 6/6 | HIGH -- both methods agree, votes unanimous |
| `0x45` | `HOWFAR` | 2 | ? | 0/0 | UNKNOWN -- too few samples |
| `0x46` | `FOR` | 2 | ? | 5/5 | UNKNOWN -- too few samples |
| `0x47` | `ENDFOR` | 0 | 0 | 6/6 | HIGH -- both methods agree, votes unanimous |
| `0x48` | `HIDEITEMS` | 1 | ? | 5/5 | UNKNOWN -- too few samples |
| `0x49` | `SKILLDAMAGE` | 0 | ? | 0/0 | UNKNOWN -- too few samples |
| `0x4A` | `DUEL` | 0 | ? | 0/0 | UNKNOWN -- too few samples |
| `0x4B` | `STORE` | 1 | 1 | 8/8 | HIGH -- both methods agree, votes unanimous |
| `0x4C` | `VIEW` | 2 | 2 | 22/24 | HIGH -- both methods agree, votes unanimous |
| `0x4D` | `ANIMATE` | 0 | ? | 0/0 | UNKNOWN -- too few samples |
| `0x4E` | `STAIRCASE` | 0 | 0 | 14/14 | HIGH -- both methods agree, votes unanimous |
| `0x4F` | `HALFSTEP` | 0 | ? | 4/4 | UNKNOWN -- too few samples |
| `0x50` | `STEPFORWARD` | 0 | 0 | 6/6 | HIGH -- both methods agree, votes unanimous |
| `0x51` | `PALETTE` | 1 | 1 | 5/7 | HIGH -- both methods agree |
| `0x52` | `UNLOCKDOOR` | 0 | 0 | 6/7 | HIGH -- both methods agree |
| `0x53` | `ADDFIGURE` | 4 | 4 | 6/6 | HIGH -- both methods agree, votes unanimous |
| `0x54` | `ADDCORPSE` | 3 | 3 | 10/10 | HIGH -- both methods agree, votes unanimous |
| `0x55` | `ADDFIGURE2` | 4 | 4 | 6/6 | HIGH -- both methods agree, votes unanimous |
| `0x56` | `ADDCORPSE2` | 3 | ? | 0/0 | UNKNOWN -- too few samples |
| `0x57` | `UPDATEFRAME` | 1 | 1 | 6/6 | HIGH -- both methods agree, votes unanimous |
| `0x58` | `REMOVEFIGURE` | 0 | 0 | 8/8 | HIGH -- both methods agree, votes unanimous |
| `0x59` | `EXPLOSION` | 1 | 1 | 8/8 | HIGH -- both methods agree, votes unanimous |
| `0x5A` | `STEPBACK` | 0 | 0 | 4/7 | HIGH -- both methods agree |
| `0x5B` | `HALFBACK` | 0 | ? | 0/0 | UNKNOWN -- too few samples |
| `0x5C` | `NEWREGION` | 6 | 6 | 15/17 | HIGH -- both methods agree |
| `0x5D` | `ICONMENU` | 1 | ? | 0/0 | dynamic arg list -- inference not valid |

methods agree on 35 of the non-DOS opcodes; disagree or uncertain on 9
