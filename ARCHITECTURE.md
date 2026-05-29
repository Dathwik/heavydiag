heavydiag/
├── simulation/          # Fake ECU that emits J1939 messages + faults
│   ├── ecu.py
│   └── j1939_encoder.py
├── comms/               # CAN/J1939 message parser & decoder
│   ├── can_interface.py
│   └── pgn_registry.json
├── diagnostics/         # The brain — DTC lookup, guided procedures
│   ├── dtc_manager.py
│   ├── guided_procedure.py
│   └── dtc_database.json
├── ui/                  # GUI (PyQt5)
│   ├── dashboard.py
│   ├── live_data_panel.py
│   └── guided_diag_panel.py
├── reports/             # PDF/HTML diagnostic report generator
│   └── report_generator.py
└── main.py