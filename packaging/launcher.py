"""Điểm vào cho PyInstaller (cần file script riêng vì __main__.py dùng import tương đối)."""

from fvpl_ittools.__main__ import main

raise SystemExit(main())
