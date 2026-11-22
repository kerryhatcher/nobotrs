# Offline copyediting pilot

On 2026-11-21 a separate Rust release executable ran Harper Core 3.2.0 with its curated British-English linter and PlainEnglish parser. It reused one dictionary and linter across eight single-sentence inputs. The numbers below describe this workstation run. The four positive cases were selected to exercise known error types.

| Input | Intended result | Harper findings |
|---|---|---|
| That’s a the state estimate. | Adjacent articles | 0 |
| We recieved the report. | Spelling | 1 |
| The team copied teh file. | Spelling | 2 |
| The board adopted an policy. | Article agreement | 1 |
| The colour matches the catalogue. | Accept British English | 0 |
| Still short. | Accept deliberate fragment | 0 |
| The board approved the revised policy. | Accept | 0 |
| The budget estimate includes repairs. | Accept | 0 |

Harper flagged three of four seeded sentences and none of four controls. Initialization took 521 ms. Per-sentence parsing and linting took 0.76–15.30 ms in that run. The standalone Cargo release executable occupied 18,591,232 bytes with the toolchain's default release profile. That measures the pilot executable, not the incremental size of adding Harper to nobotrs under its size-optimized profile. Keep Harper outside the default dependency set pending a larger representative comparison. The native rules must independently catch the fixture's adjacent articles. [Harper Core API](https://docs.rs/harper-core/3.2.0/harper_core/)
