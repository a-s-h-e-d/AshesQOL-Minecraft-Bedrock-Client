# Memory recon notes: Bedrock 1.26.63 (GDK build, Minecraft.Windows.exe)

> The `tools/` scripts mentioned below were the author's private research helpers and aren't part of this repository.

Heap addresses are from a single session and change on restart. Layouts, offsets and module RVAs carry over.
The module base was the same across a game restart (Windows only re-randomizes it on reboot).

## LocalPlayer (Actor) object
- Recognized by its vtable at **module + 0xF0C57D0**. The game strips RTTI, so there are no class names.
- Candidate static chains (`[[base+rva]+off...]`) are in `ashesqol/data/offsets.json`. The reader tries each one
  and keeps the first that leads to the right vtable. Chain #0 = `[[base+0x128C4B18]+0x638]`.
  **Not yet confirmed across a restart.**
- The actor holds direct pointers to its built-in ECS components:

| Actor + | Component | Layout |
|---|---|---|
| 0x240 | StateVectorComponent (stride 0x24) | pos @0, posPrev @0xC, posDelta @0x18 (Vec3 floats). For the player, pos.y is at **eye height** |
| 0x248 | AABBShapeComponent (stride 0x20) | min @0, max @0xC (Vec3), width @0x18, height @0x1C. min.y = feet |
| 0x250 | ActorRotationComponent (stride 0x10) | pitch @0, yaw @4, prevPitch @8, prevYaw @0xC |

- Each component's pool is a dense array. Other actors' entries sit next to the player's (the player was index 0 in both sessions).
- Writing to the client position teleports the view, but the integrated server pulls the player back. Read-only use is fine.

- Static chain confirmed across a restart: `[[base+0x1295B630]+0x330]`. The other three candidates broke.
- Actor + 0x210: MSVC `std::string` type id (`minecraft:zombie`). Players carry a suffix like `minecraft:player.0.persona-…`.
- Different classes have different vtables, but some share one (cow and chicken), so use the string for the type.

## Actor list (client registry)
- An EnTT storage of `Actor*`. Its object vtable is **module + 0xF0AE470**. It's allocated with `make_shared`, so a control block sits 0x10 before it.

| Storage + | Field |
|---|---|
| 0x00 | vtable |
| 0x08 / 0x10 / 0x18 | sparse page vector |
| 0x20 / 0x28 / 0x30 | packed `entt::entity` (u32) vector: count = (end - begin) / 4 |
| 0x38 | type_info*, then mode, then head (0x3FFFF) |
| 0x50 / 0x58 / 0x60 | payload page vector. page[i] is an array of Actor* (1024 per page assumed) |

- The table order matches the StateVector pool order. The local player was index 0.
- Single-player has **two** such storages (client and server registry). Pick the one whose table contains the local player.
- Candidate chains (not yet confirmed across a restart): `[[[[base+0x128EF288]+0x8]+0x1E8]+0x1F0]` and `[[[[base+0x1296CFB8]+0x2F8]+0x38]+0x60]`.
- Fallback: scan for the vtable qword (about 26 s, run in the background).
- Reading 22 actors takes about 0.4 ms per frame.

## How it was found
1. Cheat Engine: float scan on Y, then bisect by writing values. That gave posPrev.y.
2. `find_player.py`-style scan for (pos, posPrev, delta) records filtered by 0x24-stride neighbours. That gave the pool entry.
3. Searched for qwords equal to the pool entry. A hit at object+0x240, where qword0 of the object is a module pointer (vtable), turned out to be the Actor.
4. `tools/ptrpath.py` on the Actor address found the static chains (CE's level-5 pointer scan found nothing, because the ECS chain is deep).

5. Actor list: found the actors owning neighbouring StateVector entries (qword == entry at obj+0x240), then searched
   for contiguous runs of Actor* (a 23-long run = the storage page), then for the vectors referencing it (the storage object).

## Arena lookup (replaces static chains, 2026-11-12)
- Static chains to the LocalPlayer and to the actor storage broke between launches, because they run through containers that get reordered.
- The player is always at **(16 MB-aligned segment) + 0x122000**. Seen at 0x41C28122000, 0x36C64122000, 0x57E74122000 and 0x57E26122000. The last one is only 32 MB-aligned, so probe every 16 MB.
- The actor storage sits in the same segment, in the first 4 MB (+0x30990, +0x30F90, +0x40F90).
- Lookup takes about 100-200 ms. If it misses, a full background scan for both vtables runs (about 20-30 s; 3.25 GB at about 200 MB/s through ReadProcessMemory).

## Realms (2026-11-12)
- The local player is a **different class**: vtable **module + 0xF2DFEF0** (single-player is 0xF0C57D0). Component layout is identical.
- On a Realm it was at segment + 0x44B400, so the single-player +0x122000 shortcut doesn't apply.
- The client actor storage has the same vtable (0xF0AE470) and the local player is **entry 0**, but it sits at the start of some *other* 16 MB segment (+0x8C490).
- Lookup when the shortcut misses: a background search of the first 2 MB of every 16 MB segment for the storage vtable (about 4 s on a Realm), then the storage entry 0 whose vtable is a known player class. A full scan is the last resort. Searches back off from 60 s up to 10 min.
- A stale storage from an earlier world can still hold the vtable with dangling pointers. The entry-0 check rejects it.

## Blocks (2026-11-13)
Found from a test build (4 diamond blocks plus a chest at y 104) and validated by decoding it back exactly.

- **Chunk (LevelChunk)**: no vtable. Pooled in 0x1C00-byte slots, about 1900 chunks in a few pools.
  It's found through a member object with vtable **module + 0xF1AD490 at chunk + 0x1898**.
  - +0x78: ChunkPos (int x, int z)
  - +0x1C8: `std::vector<SubChunk>`, 0x68 bytes each, 24 in the overworld (section s covers y = -64 + 16*s)
  - +0x1438: block-actor map, an `unordered_map<ChunkBlockPos, shared_ptr<BlockActor>>`. The key is u8 x, u8 z, u16 y counted from -64.
  - Single-player has a client and a server copy of each nearby chunk, so dedupe by ChunkPos.
- **SubChunk**: +0x20 layer 0 storage, +0x28 layer 1 (water and waterlogging), +0x30 a second pointer to layer 0.
- **Storage**: the vtable selects bits per block:

  | vtable (module +) | bits/block |
  |---|---|
  | 0xF27D520 | 0 |
  | 0xF27D5D0 | 1 |
  | 0xF27D680 | 2 |
  | 0xF27D730 | 3 |
  | 0xF27D7E0 | 4 |
  | 0xF27D890 | 5 |
  | 0xF27D940 | 6 |

  - Words are u32 at +0x8, with floor(32/bits) blocks per word (no straddling). Index = x*256 + z*16 + y.
  - After the words comes an **8-aligned** palette of `Block*` with capacity 2^bits, then a u64 palette size.
  - 0 bits means the whole section is one block, stored as one `Block*` at +0x8.
- **Block**: vtable module + 0xF1831C8. Block + 0x68 points to the BlockLegacy, and the `std::string` at legacy + 0xE8 is the name (e.g. `minecraft:diamond_block`).
  The 0x20-byte objects with vtable 0xF105180 that also point to legacies are registry entries, not palette blocks.
- What didn't work: searching for the packed array with an all-air assumption. The test section was a hillside with 9 block types.
  What worked was anchoring on the chest's BlockActor (BlockPos ints at +0x8), then its map node, then the chunk.
- The scanner (`game/block_scanner.py`) does one full search for the member vtable (about 35 s), then re-reads the pool runs every second.
  It caches per-section decoding while the bytes are unchanged.
- **Dimensions**: chunk + 0x58 = `Dimension*`. The player has the same pointer at actor + 0x1F0. The Dimension's `std::string` name at +0x20 is 'Overworld', 'Nether' or 'TheEnd'.
  BlockESP keeps only chunks whose Dimension* equals the player's. In single-player that also drops the integrated server's copies, which have their own Dimension objects. The HUD uses the name for the Nether/Overworld coordinate conversion.
- An 8-bit storage (vtable 0xF27D9F0) was learned at runtime on a Realm and added to offsets.json.

## Performance notes (2026-11-13)
- A single ReadProcessMemory call occasionally stalls for 10-20 ms (median about 5-40 µs).
  Reading on the overlay's frame turned each stall into a visible hitch. All game reading now runs on `game/reader.py` (about 250 Hz), and the overlay draws the latest snapshot.
  ReadProcessMemory releases the GIL.
- The Realm's actor table had 80 entries, of which only about 11 were actors. Non-actors are skipped for 2 s after one failed check.
- Block scanner: rereading all chunk pools every second was 1.6 GB/s. Now it remembers chunk addresses, rediscovers every 10 s with small reads, and yields the GIL. A cycle went from 1.3 s to 50 ms.
  Full memory scans read 4 MB at a time and yield. `sys.setswitchinterval(0.001)`.
- Result over 1500 frames: frames over 16 ms went from about 80 to 2. Typical frame 3.2 ms.
- Open: the per-frame camera storage wasn't found in the Nether (only 1 storage had the vtable), so turning there falls back to the tick rotation.

## Smoothing
- The client ticks at 20 TPS and renders at posPrev + (pos - posPrev) * alpha.
- The overlay estimates alpha from when positions change (TickClock: a phase-locked 50 ms rhythm) and applies the same blend.
- In simulation the error dropped from 0.1-0.2 blocks to about 0.01 at 4 blocks/s.

## Camera rotation (2026-11-13)
- ActorRotationComponent (pitch, yaw, prevPitch, prevYaw) changes **once per tick**, about every 47 ms. prev always equals the last tick's value.
- `tools/camera_probe.py` searched ±32 MB around the player for per-frame yaw, radians or forward-vector values while turning. Every value that followed the yaw changed at tick rate too, so nothing nearby updates per frame.
- Blending prevYaw → yaw was tried and made things **worse**: the real camera is *ahead* of the tick value, so blending only added lag. It was removed.
- **Per-frame rotation found**: a second EnTT storage with vtable **module + 0xF0AED00**, in another registry (40 entities, not the client actor registry). Its entry 0 is the local player's (pitch, yaw, pitch, yaw) and it updates at frame rate (about 70/s vs 22/s).
  - That vtable is shared by many component storages, including the client's tick-rate rotation storage. So the right one is picked by elimination: valid count, not the client tick storage, and entry 0 within 10° of the tick rotation.
  - Found with `tools/camera_probe2.py` (still poses → full scan → recheck) plus `tools/camera_spin.py` (page-batched rate measurement while spinning).
  - Lookup is a full scan (about 30 s) once per world in `game/camera_rotation.py`, with backoff if it's missing. It falls back to the tick value if they disagree by more than 45°.
  - Confirmed working on Realms too (2026-11-13), so it is a client-side registry, not the integrated server.

## TODO
- The actor storage chains did **not** survive a restart (the 25 s fallback scan kicked in). Find a stable route,
  for example from the LocalPlayer object (EntityContext -> registry -> pools), or rerun ptrpath across two sessions.
- Interpolate entity and player positions between ticks (posPrev -> pos) to remove the ESP trailing lag.
- Player names for other players (nameTag), item names, health.
- Dimension, health, camera / view matrix (the current camera is rebuilt from pos+yaw/pitch+FOV).
- Smooth movement between 20 TPS ticks (interpolate posPrev -> pos).
