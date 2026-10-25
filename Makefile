CC = $(CURDIR)/build/toolchain/bin/x86_64-linux-musl-gcc
HOSTCC = cc
CFLAGS = -O2 -Wall -Wextra -Werror

.PHONY: all check target-check build toolchain initramfs run media boot-check previews ui-check
all: build
toolchain:
	./scripts/build-toolchain.sh
build:
	./build.sh
build/ominx: src/core/ominx.c src/lib/parse.c src/lib/files.c src/lib/parse.h src/lib/files.h src/lib/session.c src/lib/session.h src/lib/control.c src/lib/control.h src/lib/pe.c src/lib/pe.h
	mkdir -p build
	$(CC) $(CFLAGS) -static -o $@ $(filter %.c,$^)
build/ominx-files: src/files/main.c src/lib/files.c src/lib/files.h
	mkdir -p build
	$(CC) $(CFLAGS) -static -o $@ $(filter %.c,$^)
build/ominx-control: src/control/main.c src/lib/control.h src/lib/session.h
	mkdir -p build
	$(CC) $(CFLAGS) -static -o $@ $(filter %.c,$^)
build/ominx-login: src/login/broker.c src/login/login.c src/login/login.h
	mkdir -p build
	$(CC) $(CFLAGS) -static -o $@ $(filter %.c,$^)
build/ominx-seat: src/login/seat.c src/lib/control.c src/lib/control.h src/lib/session.h src/login/login.h src/lib/gamesched.c src/lib/gamesched.h src/lib/gamedb.c src/lib/gamedb.h
	mkdir -p build
	$(CC) $(CFLAGS) -static -o $@ $(filter %.c,$^)
build/ominx-passwd: src/login/passwd.c src/login/login.c src/login/login.h
	mkdir -p build
	$(CC) $(CFLAGS) -static -o $@ $(filter %.c,$^)
build/ominx-login-probe: src/login/probe.c src/login/login.c src/login/login.h
	mkdir -p build
	$(CC) $(CFLAGS) -static -o $@ $(filter %.c,$^)
# Same source, target toolchain, service checks bypassed: runs the real musl crypt.
build/ominx-login-test: src/login/broker.c src/login/login.c src/login/login.h
	mkdir -p build
	$(CC) $(CFLAGS) -DOMINX_LOGIN_TEST -static -o $@ $(filter %.c,$^)
build/ominx-win: src/win/win.c src/lib/pe.c src/lib/pe.h src/lib/gamedb.c src/lib/gamedb.h src/lib/gamesched.c src/lib/gamesched.h src/lib/winproto.h
	mkdir -p build
	$(CC) $(CFLAGS) -static -o $@ $(filter %.c,$^)
build/ominx-wined: src/win/wined.c src/lib/pe.c src/lib/pe.h src/lib/gamedb.c src/lib/gamedb.h src/lib/gamesched.c src/lib/gamesched.h src/lib/winproto.h
	mkdir -p build
	$(CC) $(CFLAGS) -static -o $@ $(filter %.c,$^)
build/ominx-winsetup: src/win/winsetup.c src/lib/winproto.h src/lib/session.h src/lib/gamesched.c src/lib/gamesched.h src/lib/gamedb.c src/lib/gamedb.h
	mkdir -p build
	$(CC) $(CFLAGS) -static -o $@ $(filter %.c,$^)
# Same sources with root/service-context checks bypassed; host tests drive
# them against a stub runtime. Never packaged.
# Same client with the game-policy fixture hooks (OMINX_GAMES_DIR, OMINX_SYSROOT).
# Never packaged; the shipped ominx-win ignores those variables.
build/ominx-win-test: src/win/win.c src/lib/pe.c src/lib/pe.h src/lib/gamedb.c src/lib/gamedb.h src/lib/gamesched.c src/lib/gamesched.h src/lib/winproto.h
	mkdir -p build
	$(CC) $(CFLAGS) -DOMINX_WIN_TEST -static -o $@ $(filter %.c,$^)
build/ominx-wined-test: src/win/wined.c src/lib/pe.c src/lib/pe.h src/lib/gamedb.c src/lib/gamedb.h src/lib/gamesched.c src/lib/gamesched.h src/lib/winproto.h
	mkdir -p build
	$(CC) $(CFLAGS) -DOMINX_WINED_TEST -static -o $@ $(filter %.c,$^)
build/ominx-gamesched-test: src/lib/gamesched-test.c src/lib/gamedb.c src/lib/gamedb.h src/lib/gamesched.c src/lib/gamesched.h
	mkdir -p build
	$(CC) $(CFLAGS) -static -o $@ $(filter %.c,$^)
build/ominx-winsetup-test: src/win/winsetup.c src/lib/winproto.h src/lib/session.h
	mkdir -p build
	$(CC) $(CFLAGS) -DOMINX_WINSETUP_TEST -static -o $@ $(filter %.c,$^)
initramfs: build/ominx build/ominx-files build/ominx-control build/ominx-win build/ominx-wined build/ominx-winsetup scripts/make-initramfs.py
	mkdir -p build/win-stage
	cp build/ominx-win build/ominx-wined build/ominx-winsetup build/win-stage/
	mkdir -p build/win-stage/games && cp compat/games/*.game build/win-stage/games/
	python3 scripts/make-initramfs.py build/ominx build/initramfs.cpio.gz build/ominx-files build/ominx-control --win-dir build/win-stage
build/host/ominx: src/core/ominx.c src/lib/parse.c src/lib/files.c src/lib/parse.h src/lib/files.h src/lib/session.c src/lib/session.h src/lib/control.c src/lib/control.h src/lib/pe.c src/lib/pe.h
	mkdir -p build/host
	$(HOSTCC) $(CFLAGS) -static -o $@ $(filter %.c,$^)
build/host/ominx-files: src/files/main.c src/lib/files.c src/lib/files.h
	mkdir -p build/host
	$(HOSTCC) $(CFLAGS) -static -o $@ $(filter %.c,$^)
build/host/ominx-control: src/control/main.c src/lib/control.h src/lib/session.h
	mkdir -p build/host
	$(HOSTCC) $(CFLAGS) -static -o $@ $(filter %.c,$^)
build/host/ominx-login-test: src/login/broker.c src/login/login.c src/login/login.h
	mkdir -p build/host
	$(HOSTCC) $(CFLAGS) -DOMINX_LOGIN_TEST -static -o $@ $(filter %.c,$^) -lcrypt
build/host/ominx-passwd: src/login/passwd.c src/login/login.c src/login/login.h
	mkdir -p build/host
	$(HOSTCC) $(CFLAGS) -static -o $@ $(filter %.c,$^) -lcrypt
build/host/ominx-win: src/win/win.c src/lib/pe.c src/lib/pe.h src/lib/gamedb.c src/lib/gamedb.h src/lib/gamesched.c src/lib/gamesched.h src/lib/winproto.h
	mkdir -p build/host
	$(HOSTCC) $(CFLAGS) -DOMINX_WIN_TEST -static -o $@ $(filter %.c,$^)
build/host/ominx-wined-test: src/win/wined.c src/lib/pe.c src/lib/pe.h src/lib/gamedb.c src/lib/gamedb.h src/lib/gamesched.c src/lib/gamesched.h src/lib/winproto.h
	mkdir -p build/host
	$(HOSTCC) $(CFLAGS) -DOMINX_WINED_TEST -static -o $@ $(filter %.c,$^)
build/host/ominx-winsetup-test: src/win/winsetup.c src/lib/winproto.h src/lib/session.h
	mkdir -p build/host
	$(HOSTCC) $(CFLAGS) -DOMINX_WINSETUP_TEST -static -o $@ $(filter %.c,$^)
build/host/ominx-gamesched-test: src/lib/gamesched-test.c src/lib/gamedb.c src/lib/gamedb.h src/lib/gamesched.c src/lib/gamesched.h
build/host/ominx-updatepolicy-test: src/lib/updatepolicy-test.c src/lib/updatepolicy.c src/lib/updatepolicy.h
	mkdir -p build/host
	$(HOSTCC) $(CFLAGS) -o $@ $(filter %.c,$^)
	mkdir -p build/host
	$(HOSTCC) $(CFLAGS) -static -o $@ $(filter %.c,$^)
check: build/host/ominx build/host/ominx-files build/host/ominx-control build/host/ominx-login-test build/host/ominx-passwd build/host/ominx-win build/host/ominx-wined-test build/host/ominx-winsetup-test build/host/ominx-gamesched-test build/host/ominx-updatepolicy-test
	OMINX_CONTROL_BINARY=$(CURDIR)/build/host/ominx-control OMINX_FILES_BINARY=$(CURDIR)/build/host/ominx-files OMINX_TEST_BINARY=$(CURDIR)/build/host/ominx OMINX_WIN_BINARY=$(CURDIR)/build/host/ominx-win OMINX_WINED_BINARY=$(CURDIR)/build/host/ominx-wined-test OMINX_WINSETUP_BINARY=$(CURDIR)/build/host/ominx-winsetup-test OMINX_GAMESCHED_BINARY=$(CURDIR)/build/host/ominx-gamesched-test OMINX_UPDATEPOLICY_BINARY=$(CURDIR)/build/host/ominx-updatepolicy-test python3 -m unittest discover -s tests -v
target-check: initramfs build/ominx-login build/ominx-seat build/ominx-passwd build/ominx-login-probe build/ominx-login-test build/ominx-win-test build/ominx-wined-test build/ominx-winsetup-test build/ominx-gamesched-test
	OMINX_CONTROL_BINARY=$(CURDIR)/build/ominx-control OMINX_FILES_BINARY=$(CURDIR)/build/ominx-files OMINX_TEST_BINARY=$(CURDIR)/build/ominx OMINX_LOGIN_BINARY=$(CURDIR)/build/ominx-login-test OMINX_PASSWD_BINARY=$(CURDIR)/build/ominx-passwd OMINX_WIN_BINARY=$(CURDIR)/build/ominx-win-test OMINX_WINED_BINARY=$(CURDIR)/build/ominx-wined-test OMINX_WINSETUP_BINARY=$(CURDIR)/build/ominx-winsetup-test OMINX_GAMESCHED_BINARY=$(CURDIR)/build/ominx-gamesched-test python3 -m unittest discover -s tests -v
media:
	./scripts/build-media.sh
run:
	@test -f build/ominx-x86_64.iso || (echo 'Run make toolchain build first'; exit 1)
	qemu-system-x86_64 -m 512 -cdrom build/ominx-x86_64.iso -boot d -serial stdio -nic none
boot-check:
	python3 scripts/test-platforms.py

# Preview images in docs/previews (needs Pillow: pip install pillow).
previews:
	python3 scripts/render-previews.py

# Game library QML checks (needs PySide6). Set OMINX_QT_STUB_DIR only in sandboxes
# without a GL/EGL/xkb/dbus runtime. Also refreshes the game library screenshots.
ui-check:
	$${OMINX_UI_PYTHON:-python3} tests/ui/test_game_library.py
