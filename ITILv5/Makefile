.PHONY: up down restart status logs test clean

PYTHON ?= ../.venv/bin/python
APP    ?= app.py
PORT   ?= 5002
PID    := /tmp/itil-app.pid

up:
	@echo "[ITILv5] starting on http://127.0.0.1:$(PORT)"
	@$(PYTHON) $(APP)

down:
	@if [ -f $(PID) ]; then kill $$(cat $(PID)) 2>/dev/null && rm $(PID); echo "[ITILv5] stopped"; else echo "[ITILv5] no pid file"; fi

restart: down up

status:
	@curl -s http://127.0.0.1:$(PORT)/api/health | python3 -m json.tool 2>/dev/null || echo "not running"

logs:
	@tail -50 /tmp/itil-app.out.log /tmp/itil-app.err.log 2>/dev/null || echo "no logs"

test:
	@echo "[ITILv5] smoke test"
	@$(PYTHON) -c "import app; app.init_db(); print('init_db OK')"

clean:
	@rm -f exam.sqlite /tmp/itil-app.pid
	@echo "[ITILv5] reset DB + pid file (run 'make up' to recreate)"