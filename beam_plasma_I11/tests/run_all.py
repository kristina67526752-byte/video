"""Запуск всех проверок без pytest:  python tests/run_all.py"""
import importlib.util
import os
import sys
import time
import traceback

here = os.path.dirname(os.path.abspath(__file__))
ok = fail = 0
for fn in sorted(os.listdir(here)):
    if not (fn.startswith("test_") and fn.endswith(".py")):
        continue
    spec = importlib.util.spec_from_file_location(fn[:-3], os.path.join(here, fn))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for name in dir(mod):
        if name.startswith("test_"):
            t0 = time.time()
            try:
                getattr(mod, name)()
                ok += 1
                print(f"  OK    {fn}::{name}  ({time.time() - t0:.1f} с)")
            except Exception:
                fail += 1
                print(f"  FAIL  {fn}::{name}")
                traceback.print_exc()
print(f"\nпройдено {ok}, ошибок {fail}")
sys.exit(1 if fail else 0)
