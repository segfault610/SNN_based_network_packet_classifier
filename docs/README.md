# Documentation

| document | read it for |
|---|---|
| [design.md](design.md) | **what the design is**: system architecture diagrams (ASIC / Tang Nano 9K / Chameleon96), the engine's block diagram, the life of a frame, **every signal** of every module and board top, register maps, the 64 input features, the network maths, sizes, the UART and kernel protocols |
| [verification_guide.md](verification_guide.md) | **how to test it in every workflow**: laptop simulation (vsim), Cadence on the uni server (xrun, Genus, Conformal, Innovus), Tang Nano 9K over UART, Chameleon96 with Linux, sky130 on GitHub Actions; the stimuli and checks of every testbench; sign-off checklist |
| [simulation_explained.md](simulation_explained.md) | **what the simulation means**: the golden model, every test-vector file, the 600 frames, the 10 ASIC tests in plain language, the detection numbers, how to read the SimVision waveform |
| [functional_verification.md](functional_verification.md) | the compact ASIC test table (T1–T10) with expected xrun output |
| [chameleon96_deploy.md](chameleon96_deploy.md) | Chameleon96 bring-up in detail |
| [chameleon96_wifi.md](chameleon96_wifi.md) | analysis of the on-board WiFi (SDIO through the FPGA) |
| [../asic/README.md](../asic/README.md) | Cadence flow scripts: every command and output file |
| [../asic/openlane/README.md](../asic/openlane/README.md) | sky130 LibreLane flow on GitHub Actions |

Screenshots of results live in [img/](img/).
