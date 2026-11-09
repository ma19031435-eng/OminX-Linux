"""Forge 1.0: language semantics, checker, project tools, the OminXOS gate, and
the OPKGX forge runner.

Drives build/host/ominx-forge-test (OMINX_FORGE_BINARY), which reads the platform
identity from a fixture file, and build/host/ominx-forge (OMINX_FORGE_PROD_BINARY),
the shipped build that must refuse to run off OminXOS. The language is specified
in docs/forge-language.md, the tools in docs/forge-studio.md, and packaging in
docs/opkgx-format.md."""
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = os.environ.get('OMINX_FORGE_BINARY', str(ROOT / 'build/host/ominx-forge-test'))
PROD = os.environ.get('OMINX_FORGE_PROD_BINARY', str(ROOT / 'build/host/ominx-forge'))
OPKGX = os.environ.get('OMINX_OPKGX_BINARY', str(ROOT / 'build/host/ominx-opkgx'))


class ForgeCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.os_ominx = self.root / 'os-release-ominx'
        self.os_ominx.write_text('NAME=OminX\nID=ominx\n')
        self.os_other = self.root / 'os-release-other'
        self.os_other.write_text('NAME=Ubuntu\nID=ubuntu\n')

    def tearDown(self):
        self._tmp.cleanup()

    def env(self, identity=None):
        env = dict(os.environ)
        env['OMINX_FORGE_OS_RELEASE'] = str(identity or self.os_ominx)
        return env

    def forge(self, *args, stdin=None, identity=None, timeout=60):
        return subprocess.run([BIN, *args], input=stdin, capture_output=True, text=True,
                              env=self.env(identity), timeout=timeout)

    def program(self, source, name='t.fg'):
        path = self.root / name
        path.write_text(source)
        return path

    def run_source(self, source, name='t.fg'):
        return self.forge('run', str(self.program(source, name)))

    def check_source(self, source, name='t.fg'):
        return self.forge('check', str(self.program(source, name)), '--json')


class Language(ForgeCase):
    def assertOutput(self, source, expected):
        r = self.run_source(source)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, expected)

    def test_arithmetic_and_precedence(self):
        self.assertOutput('fn main() { print(1 + 2 * 3, (1 + 2) * 3, 10 - 4 - 3) }', '7 9 3\n')

    def test_integer_and_float_semantics(self):
        self.assertOutput('fn main() { print(7 / 2, 7 % 3, -7 % 3, 7.0 / 2, 1.0 + 2, 2.5 * 2) }',
                          '3 1 -1 3.5 3.0 5.0\n')

    def test_comparisons_and_equality(self):
        self.assertOutput('fn main() { print(1 == 1.0, 1 != 2, "a" < "b", "abc" > "abd", 2 >= 2, nil == nil) }',
                          'true true true false true true\n')
        self.assertOutput('fn main() { print(1 == "1", [1] == [1]) }', 'false true\n')

    def test_structural_equality_for_lists_and_maps(self):
        self.assertOutput('fn main() {\n print([1, [2, "a"]] == [1, [2, "a"]], [1] == [1, 2], {"a": 1, "b": 2} == {"b": 2, "a": 1})\n'
                          ' print({"a": 1} == {"a": 2}, {"a": 1} == {"b": 1}, [1] == {}, [1] != [1])\n'
                          ' let self = []\n push(self, self)\n print(self == self) }',
                          'true false true\nfalse false false false\ntrue\n')

    def test_boolean_operators_are_strict(self):
        self.assertOutput('fn main() { print(not false and true, false or true, true and false) }',
                          'true true false\n')
        r = self.run_source('fn main() { print(1 and true) }')
        self.assertEqual(r.returncode, 1)
        self.assertIn("'and' operand must be true or false, not int", r.stderr)

    def test_short_circuit(self):
        self.assertOutput('fn boom() { error("should not run") }\n'
                          'fn main() { print(false and boom(), true or boom()) }', 'false true\n')

    def test_strings_and_escapes(self):
        self.assertOutput('fn main() { print("a\\tb\\n\\"q\\"\\\\") }', 'a\tb\n"q"\\\n')
        self.assertOutput('fn main() { print("x" + "y", len("héllo")) }', 'xy 6\n')

    def test_float_display(self):
        self.assertOutput('fn main() { print(1.0, 0.5, 100.0, 1250.0 == 1250.0) }', '1.0 0.5 100.0 true\n')

    def test_lists(self):
        self.assertOutput('fn main() { let xs = [1, 2]\n push(xs, 3)\n xs[0] = 9\n print(xs, len(xs), xs[2], pop(xs), xs) }',
                          '[9, 2] 3 3 3 [9, 2]\n')
        self.assertOutput('fn main() { print([1] + [2, 3], [], [[1], "a"]) }', '[1, 2, 3] [] [[1], "a"]\n')

    def test_maps(self):
        src = ('fn main() { let m = {"b": 2}\n m["a"] = 1\n m["b"] = 3\n'
               ' print(m, len(m), has(m, "a"), has(m, "z"), keys(m), remove(m, "a"), remove(m, "a"), m) }')
        self.assertOutput(src, '{"b": 3} 2 true false ["b", "a"] true false {"b": 3}\n')

    def test_string_indexing_and_iteration(self):
        self.assertOutput('fn main() { let s = "abc"\n print(s[1])\n for c in s { print(c) } }', 'b\na\nb\nc\n')

    def test_builtins_on_strings(self):
        self.assertOutput(
            'fn main() { print(split("a,b,,c", ","), join(["x", 1, nil], "-"), upper("ab"), lower("AB"),'
            ' trim("  hi \\n"), contains("hello", "ell"), contains([1, 2], 2), starts_with("abc", "ab"),'
            ' ends_with("abc", "bc"), ends_with("a", "abc"), replace("a-b-a", "a", "X"), substr("abcdef", 2, 3)) }',
            '["a", "b", "", "c"] x-1-nil AB ab hi true true true true false X-b-X cde\n')

    def test_numeric_builtins(self):
        self.assertOutput('fn main() { print(abs(-3), abs(-2.5), min(2, 5), max(2.5, 1), floor(2.9), sqrt(16.0), range(3)) }',
                          '3 2.5 2 2.5 2 4.0 [0, 1, 2]\n')

    def test_conversions(self):
        self.assertOutput('fn main() { print(int("42"), int(3.9), int(true), float("2.5"), float(2), str([1, "a"]), str(2.0), type(nil), type(fn() {})) }',
                          '42 3 1 2.5 2.0 [1, "a"] 2.0 nil fn\n')

    def test_functions_recursion_and_hoisting(self):
        self.assertOutput('fn main() { print(fib(15), later(2)) }\n'
                          'fn fib(n) { if n < 2 { return n } return fib(n - 1) + fib(n - 2) }\n'
                          'fn later(x) { return x * 10 }\n', '610 20\n')

    def test_closures_keep_state(self):
        self.assertOutput('fn make() { let n = 0\n return fn() { n = n + 1\n return n } }\n'
                          'fn main() { let c = make()\n c()\n c()\n print("count", c()) }', 'count 3\n')

    def test_while_break_continue(self):
        self.assertOutput('fn main() { let i = 0\n let out = []\n'
                          ' while true { i = i + 1\n if i > 6 { break }\n if i % 2 == 0 { continue }\n push(out, i) }\n'
                          ' print(out) }', '[1, 3, 5]\n')

    def test_for_loops_over_lists_maps_and_ranges(self):
        self.assertOutput('fn main() { let total = 0\n for i in range(5) { if i == 3 { continue }\n total = total + i }\n'
                          ' for k in {"a": 1, "b": 2} { print(k) }\n print(total) }', 'a\nb\n7\n')

    def test_break_inside_for_inside_function(self):
        self.assertOutput('fn first_even(xs) { for x in xs { if x % 2 == 0 { return x } }\n return nil }\n'
                          'fn main() { print(first_even([1, 3, 4, 6]), first_even([1])) }', '4 nil\n')

    def test_return_value_must_share_its_line(self):
        # A bare return ends the call with nil; the next line is not its value.
        self.assertOutput('fn f() { return\n print("after") }\n'
                          'fn main() { print(f()) }', 'nil\n')

    def test_block_scope_and_shadowing(self):
        self.assertOutput('fn main() { let x = 1\n if true { let x = 2\n print(x) }\n print(x) }', '2\n1\n')

    def test_parameters_can_be_redeclared_in_the_body(self):
        self.assertOutput('fn f(n) { let m = n * 2\n return m }\nfn main() { print(f(4)) }', '8\n')

    def test_exit_code(self):
        r = self.run_source('fn main() { print("bye")\n exit(7) }')
        self.assertEqual(r.returncode, 7)
        self.assertEqual(r.stdout, 'bye\n')

    def test_assert(self):
        r = self.run_source('fn main() { assert(1 == 2, "math is broken") }')
        self.assertEqual(r.returncode, 1)
        self.assertIn('assertion failed: math is broken', r.stderr)

    def test_error_builtin(self):
        r = self.run_source('fn main() { error("custom failure") }')
        self.assertEqual(r.returncode, 1)
        self.assertIn('t.fg:1:', r.stderr)
        self.assertIn('custom failure', r.stderr)


class RuntimeErrors(ForgeCase):
    def assertRuntimeError(self, source, message, line=None):
        r = self.run_source(source)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(message, r.stderr)
        if line is not None:
            self.assertIn(f't.fg:{line}:', r.stderr)

    def test_division_by_zero(self):
        self.assertRuntimeError('fn main() { print(1 / 0) }', 'division by zero', 1)
        self.assertRuntimeError('fn main() { print(1 % 0) }', 'division by zero')

    def test_index_out_of_range(self):
        self.assertRuntimeError('fn main() { let xs = [1, 2]\n print(xs[5]) }', 'index 5 is out of range for a list of length 2', 2)
        self.assertRuntimeError('fn main() { print("ab"[-1]) }', 'index -1 is out of range')

    def test_missing_map_key(self):
        self.assertRuntimeError('fn main() { let m = {"a": 1}\n print(m["b"]) }', 'no key "b" in the map', 2)

    def test_non_bool_condition(self):
        self.assertRuntimeError('fn main() { if 1 { print("x") } }', 'condition must be true or false, not int', 1)

    def test_type_errors(self):
        self.assertRuntimeError('fn main() { print(1 + "a") }', 'cannot add int and str')
        self.assertRuntimeError('fn main() { print(-"a") }', 'cannot negate str')
        self.assertRuntimeError('fn main() { print({1: 2}) }', 'map keys must be strings')
        self.assertRuntimeError('fn main() { print(len(3)) }', 'len needs a string, list or map')

    def test_integer_overflow(self):
        self.assertRuntimeError('fn main() { let n = 9223372036854775807\n print(n + 1) }', 'integer overflow in +', 2)
        self.assertRuntimeError('fn main() { print(-9223372036854775807 - 2) }', 'integer overflow in -')

    def test_bad_conversions(self):
        self.assertRuntimeError('fn main() { print(int("12x")) }', 'cannot convert "12x" to an int')
        self.assertRuntimeError('fn main() { print(float("nan")) }', 'cannot convert "nan" to a float')

    def test_arity_at_run_time(self):
        self.assertRuntimeError('fn f(a, b) { return a }\nfn main() { let g = f\n g(1) }', 'f expects 2 arguments, got 1')

    def test_calling_a_non_function(self):
        self.assertRuntimeError('fn main() { let x = 3\n x() }', 'int is not a function')

    def test_stack_overflow_is_an_error_not_a_crash(self):
        self.assertRuntimeError('fn r(n) { return r(n + 1) }\nfn main() { r(0) }', 'stack overflow: more than 400 nested calls')

    def test_runaway_memory_is_capped(self):
        r = self.run_source('fn main() { let xs = []\n while true { push(xs, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx") } }')
        self.assertEqual(r.returncode, 1)
        self.assertIn('out of memory', r.stderr)

    def test_runaway_output_is_capped(self):
        r = self.run_source('fn main() { let s = "0123456789012345678901234567890123456789012345678901234567890123"\n'
                            ' while true { print(s, s, s, s, s, s, s, s, s, s, s, s, s, s, s, s) } }', name='flood.fg')
        self.assertEqual(r.returncode, 1)
        self.assertIn('printed more than 16 MiB', r.stderr)

    def test_missing_main(self):
        r = self.run_source('fn helper() { return 1 }')
        self.assertEqual(r.returncode, 1)
        self.assertIn('no main() function', r.stderr)

    def test_deep_nesting_is_refused_without_crashing(self):
        deep = 'fn main() { print(' + '(' * 400 + '1' + ')' * 400 + ') }'
        r = self.run_source(deep)
        self.assertEqual(r.returncode, 1)
        self.assertIn('nested too deeply', r.stderr)
        self.assertNotIn('Segmentation', r.stderr)
        stmts = 'fn main() { ' + '{ ' * 300 + '}' * 300 + ' }'
        r = self.run_source(stmts)
        self.assertEqual(r.returncode, 1)
        self.assertIn('nested too deeply', r.stderr)


class Checker(ForgeCase):
    def diags(self, source, name='t.fg'):
        r = self.check_source(source, name)
        self.assertEqual(r.returncode, 1, r.stdout)
        return json.loads(r.stdout)['diagnostics']

    def messages(self, source):
        return [d['message'] for d in self.diags(source)]

    def test_clean_program_passes(self):
        r = self.check_source('fn main() { print("ok") }')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout), {'ok': True, 'diagnostics': []})

    def test_undefined_name(self):
        d = self.diags('fn main() { print(x) }')
        self.assertEqual(d[0]['message'], "undefined name 'x'")
        self.assertEqual((d[0]['line'], d[0]['col']), (1, 19))

    def test_redeclaration_in_one_scope(self):
        self.assertIn("'a' is already declared in this scope", self.messages('fn main() { let a = 1\n let a = 2 }'))

    def test_assignment_to_undeclared(self):
        self.assertIn("assignment to undeclared name 'x'", self.messages('fn main() { x = 4 }'))

    def test_break_and_continue_outside_loops(self):
        self.assertIn('break outside a loop', self.messages('fn main() { break }'))
        self.assertIn('continue outside a loop', self.messages('fn main() { continue }'))

    def test_loop_does_not_leak_into_a_nested_function(self):
        self.assertIn('break outside a loop',
                      self.messages('fn main() { while true { fn inner() { break } } }'))

    def test_return_outside_function(self):
        self.assertIn('only let, fn and import may appear at the top level',
                      self.messages('return 5\nfn main() {}'))

    def test_builtin_arity(self):
        self.assertIn('len expects 1 argument, got 2', self.messages('fn main() { print(len([], 1)) }'))
        self.assertIn('replace expects 3 arguments, got 2', self.messages('fn main() { print(replace("a", "b")) }'))

    def test_user_function_arity(self):
        self.assertIn('f expects 2 arguments, got 1', self.messages('fn f(a, b) { return a }\nfn main() { f(1) }'))

    def test_duplicate_top_level_names(self):
        self.assertIn("'f' is already defined", self.messages('fn f() {}\nfn f() {}\nfn main() {}'))

    def test_builtin_names_cannot_be_redefined_at_top_level(self):
        self.assertIn("'len' is a builtin name and cannot be redefined", self.messages('fn len() {}\nfn main() {}'))

    def test_duplicate_parameter_and_nested_function(self):
        self.assertIn("duplicate parameter 'a'", self.messages('fn f(a, a) {}\nfn main() {}'))
        self.assertIn("'g' is already declared in this scope",
                      self.messages('fn main() { let g = 1\n fn g() {} }'))

    def test_local_shadowing_builtin_is_allowed(self):
        r = self.check_source('fn main() { let len = 3\n print(len) }')
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_parse_errors_have_positions(self):
        d = self.diags('fn main() { let x = 3 +  }')
        self.assertEqual(d[0]['message'], "expected an expression but found '}'")
        self.assertEqual((d[0]['line'], d[0]['col']), (1, 26))

    def test_unterminated_string_and_bad_characters(self):
        self.assertIn('unterminated string', self.messages('fn main() { print("oops) }'))
        self.assertIn("unexpected character '@'", self.messages('fn main() { @ }'))
        self.assertIn('unknown escape sequence', self.messages('fn main() { print("\\q") }'))

    def test_statement_rules(self):
        self.assertIn('only let, fn and import may appear at the top level', self.messages('print(1)\nfn main() {}'))
        self.assertIn('invalid assignment target', self.messages('fn main() { 1 = 2 }'))
        self.assertIn('import is only allowed at the top level', self.messages('fn main() { import "x.fg" }'))

    def test_json_stays_valid_for_invalid_utf8_source(self):
        path = self.root / 'bad.fg'
        path.write_bytes(b'fn main() { \xff "x\xe2\x82" }\n')
        r = self.forge('check', str(path), '--json')
        self.assertEqual(r.returncode, 1)
        out = json.loads(r.stdout.encode('utf-8'))
        self.assertIn('unexpected byte 0xFF', out['diagnostics'][0]['message'])

    def test_text_output_uses_file_and_position(self):
        path = self.program('fn main() { print(nope) }')
        r = self.forge('check', str(path))
        self.assertEqual(r.returncode, 1)
        self.assertIn("t.fg:1:19: error: undefined name 'nope'", r.stderr)


class Imports(ForgeCase):
    def test_imports_share_declarations(self):
        (self.root / 'lib').mkdir()
        (self.root / 'lib/math.fg').write_text('fn double(x) { return x * 2 }\nlet base = 10\n')
        self.program('import "lib/math.fg"\nfn main() { print(double(base)) }', 'main.fg')
        r = self.forge('run', str(self.root / 'main.fg'))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, '20\n')

    def test_import_errors_are_reported_in_the_importing_file(self):
        self.program('import "missing.fg"\nfn main() {}', 'main.fg')
        r = self.forge('check', str(self.root / 'main.fg'), '--json')
        d = json.loads(r.stdout)['diagnostics']
        self.assertEqual(d[0]['message'], 'file not found')
        self.assertEqual((d[0]['file'], d[0]['line']), ('main.fg', 1))

    def test_import_cycle_is_refused(self):
        (self.root / 'a.fg').write_text('import "b.fg"\nfn fa() {}\n')
        (self.root / 'b.fg').write_text('import "a.fg"\nfn fb() {}\n')
        self.program('import "a.fg"\nfn main() {}', 'main.fg')
        r = self.forge('check', str(self.root / 'main.fg'), '--json')
        self.assertIn('import cycle', r.stdout)

    def test_imports_cannot_escape_the_project(self):
        self.program('import "../outside.fg"\nfn main() {}', 'main.fg')
        r = self.forge('check', str(self.root / 'main.fg'), '--json')
        self.assertIn('import path must be relative and inside the project', r.stdout)
        self.program('import "/etc/passwd"\nfn main() {}', 'abs.fg')
        r = self.forge('check', str(self.root / 'abs.fg'), '--json')
        self.assertIn('import path must be relative and inside the project', r.stdout)

    def test_imported_names_are_checked_in_one_namespace(self):
        (self.root / 'dup.fg').write_text('fn main() {}\n')
        self.program('import "dup.fg"\nfn main() {}', 'main.fg')
        r = self.forge('check', str(self.root / 'main.fg'), '--json')
        self.assertIn("'main' is already defined", r.stdout)


class Assets(ForgeCase):
    def test_read_asset_from_the_assets_folder(self):
        (self.root / 'assets').mkdir()
        (self.root / 'assets/greeting.txt').write_text('hello asset')
        self.program('fn main() { print(read_asset("greeting.txt")) }', 'main.fg')
        r = self.forge('run', str(self.root / 'main.fg'))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, 'hello asset\n')

    def test_asset_names_cannot_escape(self):
        (self.root / 'assets').mkdir()
        (self.root / 'secret.txt').write_text('nope')
        self.program('fn main() { print(read_asset("../secret.txt")) }', 'main.fg')
        r = self.forge('run', str(self.root / 'main.fg'))
        self.assertEqual(r.returncode, 1)
        self.assertIn('invalid asset name', r.stderr)
        self.assertNotIn('nope', r.stdout)
        self.program('fn main() { print(read_asset("/etc/passwd")) }', 'abs.fg')
        r = self.forge('run', str(self.root / 'abs.fg'))
        self.assertIn('invalid asset name', r.stderr)

    def test_missing_asset(self):
        self.program('fn main() { print(read_asset("none.txt")) }', 'main.fg')
        r = self.forge('run', str(self.root / 'main.fg'))
        self.assertIn('runtime error', r.stderr)
        self.assertIn('no assets folder', r.stderr)
        (self.root / 'assets').mkdir()
        r = self.forge('run', str(self.root / 'main.fg'))
        self.assertEqual(r.returncode, 1)
        self.assertIn("asset 'none.txt' is missing", r.stderr)


class TestRunner(ForgeCase):
    def test_tests_report_each_result(self):
        self.program('fn test_ok() { assert(1 + 1 == 2) }\n'
                     'fn test_bad() { assert(false, "nope") }\n'
                     'fn helper() {}\n', 'suite.fg')
        r = self.forge('test', str(self.root / 'suite.fg'))
        self.assertEqual(r.returncode, 1)
        self.assertIn('ok test_ok', r.stdout)
        self.assertIn('FAIL test_bad: suite.fg:2:23: runtime error: assertion failed: nope', r.stdout)
        self.assertIn('1 passed, 1 failed', r.stdout)

    def test_no_tests_is_an_error(self):
        self.program('fn main() {}', 'none.fg')
        r = self.forge('test', str(self.root / 'none.fg'))
        self.assertEqual(r.returncode, 1)
        self.assertIn('no test_ functions found', r.stderr)


class PlatformGate(ForgeCase):
    def test_refuses_on_other_systems(self):
        r = self.forge('run', str(self.program('fn main() {}')), identity=self.os_other)
        self.assertEqual(r.returncode, 3)
        self.assertIn('Forge runs only on OminXOS', r.stderr)

    def test_refuses_when_identity_is_missing(self):
        r = self.forge('check', str(self.program('fn main() {}')), identity=self.root / 'absent')
        self.assertEqual(r.returncode, 3)

    def test_help_and_version_do_not_need_the_platform(self):
        for cmd in ('version', 'help'):
            r = subprocess.run([BIN, cmd], capture_output=True, text=True,
                               env=self.env(self.os_other), timeout=30)
            self.assertIn(r.returncode, (0, 2), cmd)
        r = subprocess.run([BIN, 'version'], capture_output=True, text=True, env=self.env(self.os_other), timeout=30)
        self.assertIn('Forge 1.0', r.stdout)

    def test_shipped_build_refuses_on_this_host(self):
        if not Path(PROD).exists():
            self.skipTest('build/host/ominx-forge not built')
        env = dict(os.environ)
        r = subprocess.run([PROD, 'run', str(self.program('fn main() { print(1) }'))],
                           capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(r.returncode, 3)
        self.assertIn('Forge runs only on OminXOS', r.stderr)
        self.assertEqual(r.stdout, '')

    def test_shipped_build_ignores_the_test_hook(self):
        if not Path(PROD).exists():
            self.skipTest('build/host/ominx-forge not built')
        env = dict(os.environ)
        env['OMINX_FORGE_OS_RELEASE'] = str(self.os_ominx)
        r = subprocess.run([PROD, 'run', str(self.program('fn main() { print(1) }'))],
                           capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(r.returncode, 3, 'the override must exist only in the test build')


class Project(ForgeCase):
    def new_project(self, name='Puzzle Garden', ident='org.example.puzzle', version='1.2.0'):
        proj = self.root / 'proj'
        r = self.forge('new', str(proj), '--id', ident, '--name', name, '--version', version,
                       '--summary', 'Calm tile puzzles.')
        self.assertEqual(r.returncode, 0, r.stderr)
        return proj

    def test_new_creates_a_runnable_project(self):
        proj = self.new_project()
        self.assertTrue((proj / 'forge.project').is_file())
        self.assertTrue((proj / 'src/main.fg').is_file())
        self.assertTrue((proj / 'assets/README.txt').is_file())
        r = self.forge('check', str(proj))
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.forge('run', str(proj))
        self.assertEqual(r.stdout, 'Hello, OminX!\n')
        r = self.forge('test', str(proj))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('1 passed, 0 failed', r.stdout)

    def test_new_refuses_existing_folders_and_bad_arguments(self):
        proj = self.new_project()
        r = self.forge('new', str(proj), '--id', 'a.b', '--name', 'x')
        self.assertEqual(r.returncode, 1)
        r = self.forge('new', str(self.root / 'p2'), '--id', 'a.b')
        self.assertEqual(r.returncode, 2)
        r = self.forge('new', str(self.root / 'p3'), '--id', 'a.b', '--name', 'line\nbreak')
        self.assertEqual(r.returncode, 1)

    def test_project_file_errors_are_reported(self):
        proj = self.new_project()
        (proj / 'forge.project').write_text('format=2\nid=a.b\nbogus=1\nmain=../x.fg\n')
        r = self.forge('check', str(proj), '--json')
        self.assertEqual(r.returncode, 1)
        messages = [d['message'] for d in json.loads(r.stdout)['diagnostics']]
        self.assertIn('format must be 1', messages)
        self.assertIn("unknown key 'bogus'", messages)
        self.assertIn('name is required', messages)
        self.assertIn('main must be a .fg file inside src/', messages)

    def test_overlong_project_values_are_refused_not_cut(self):
        proj = self.new_project()
        (proj / 'forge.project').write_text('format=1\nid=org.example.long\nname=' + 'N' * 300 + '\nversion=1.0.0\n'
                                            'main=main.fg\n')
        r = self.forge('check', str(proj), '--json')
        self.assertEqual(r.returncode, 1)
        messages = [d['message'] for d in json.loads(r.stdout)['diagnostics']]
        self.assertIn('name is too long (at most 127 characters)', messages)

    def test_diagnostics_in_projects_are_relative_to_src(self):
        proj = self.new_project()
        (proj / 'src/main.fg').write_text('fn main() { print(missing) }\n')
        r = self.forge('check', str(proj), '--json')
        d = json.loads(r.stdout)['diagnostics'][0]
        self.assertEqual(d['file'], 'src/main.fg')

    def test_build_produces_a_valid_opkgx(self):
        proj = self.new_project()
        r = self.forge('build', str(proj))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = proj / 'build/org.example.puzzle-1.2.0.opkgx'
        self.assertTrue(out.is_file())
        self.assertEqual(list((proj / 'build').glob('.stage-*')), [])
        r = subprocess.run([OPKGX, 'validate', str(out)], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_build_refuses_broken_programs(self):
        proj = self.new_project()
        (proj / 'src/main.fg').write_text('fn main() { print(nope) }\n')
        r = self.forge('build', str(proj))
        self.assertEqual(r.returncode, 1)
        self.assertFalse((proj / 'build').exists() and list((proj / 'build').glob('*.opkgx')))

    def test_build_refuses_non_forge_files_in_src(self):
        proj = self.new_project()
        (proj / 'src/notes.txt').write_text('stray')
        r = self.forge('build', str(proj))
        self.assertEqual(r.returncode, 1)
        self.assertIn('only .fg files belong in src/', r.stderr)

    def test_build_refuses_symlinks(self):
        proj = self.new_project()
        os.symlink('/etc/passwd', proj / 'src/link.fg')
        r = self.forge('build', str(proj))
        self.assertEqual(r.returncode, 1)
        self.assertIn('symbolic links are not allowed', r.stderr)

    def test_build_is_deterministic(self):
        proj = self.new_project()
        self.forge('build', str(proj), '--out', str(self.root / 'a.opkgx'))
        self.forge('build', str(proj), '--out', str(self.root / 'b.opkgx'))
        self.assertEqual((self.root / 'a.opkgx').read_bytes(), (self.root / 'b.opkgx').read_bytes())

    def test_tree_lists_only_editable_paths(self):
        proj = self.new_project()
        (proj / 'build').mkdir(exist_ok=True)
        (proj / 'build/junk').write_text('x')
        (proj / 'stray.txt').write_text('x')
        r = self.forge('tree', str(proj), '--json')
        paths = [e['path'] for e in json.loads(r.stdout)]
        self.assertIn('src/main.fg', paths)
        self.assertIn('forge.project', paths)
        self.assertNotIn('stray.txt', paths)
        self.assertFalse(any(p.startswith('build') for p in paths))

    def test_read_and_write_are_confined_to_the_project(self):
        proj = self.new_project()
        r = self.forge('read', str(proj), 'src/main.fg')
        self.assertEqual(r.returncode, 0)
        self.assertIn('Hello', r.stdout)
        r = self.forge('write', str(proj), 'src/extra.fg', stdin='fn main() { print("extra") }\n')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.forge('run', str(proj / 'src/extra.fg')).stdout, 'extra\n')
        for bad in ('../escape.fg', '/etc/passwd', 'src/../../x.fg', 'src/a.txt', 'build/x', '.hidden', 'src/x y.fg'):
            r = self.forge('write', str(proj), bad, stdin='x')
            self.assertNotEqual(r.returncode, 0, bad)
            self.assertFalse((self.root / 'escape.fg').exists())
            r = self.forge('read', str(proj), bad)
            self.assertNotEqual(r.returncode, 0, bad)

    def test_write_replaces_atomically_and_keeps_no_temp_files(self):
        proj = self.new_project()
        self.forge('write', str(proj), 'src/main.fg', stdin='fn main() { print("v2") }\n')
        self.assertEqual(self.forge('run', str(proj)).stdout, 'v2\n')
        self.assertEqual(list((proj / 'src').glob('*.tmp-*')), [])


class OpkgxForgeRunner(ForgeCase):
    def setUp(self):
        super().setUp()
        self.home = self.root / 'home'
        self.home.mkdir()

    def opkgx(self, *args, timeout=60):
        env = dict(os.environ)
        env['HOME'] = str(self.home)
        env['OMINX_FORGE_OS_RELEASE'] = str(self.os_ominx)
        return subprocess.run([OPKGX, *args], capture_output=True, text=True, env=env, timeout=timeout)

    def test_forge_packages_install_and_run(self):
        proj = self.root / 'proj'
        self.assertEqual(self.forge('new', str(proj), '--id', 'org.example.greeter', '--name', 'Greeter').returncode, 0)
        self.assertEqual(self.forge('build', str(proj)).returncode, 0)
        pkg = proj / 'build/org.example.greeter-1.0.0.opkgx'
        r = self.opkgx('install', str(pkg))
        self.assertEqual(r.returncode, 0, r.stderr)
        registry = (self.home / '.local/share/ominx/apps/registry').read_text()
        self.assertIn('org.example.greeter 1.0.0 forge ready', registry)
        desk = (self.home / '.local/share/applications/ominx-org.example.greeter.desktop').read_text()
        self.assertIn('X-OminX-Runner=forge', desk)
        self.assertIn('Exec=ominx-opkgx run --notify org.example.greeter', desk)
        r = self.opkgx('run', 'org.example.greeter')
        self.assertEqual(r.returncode, 0, r.stderr)
        # A desktop launch has no terminal: the program's output lands in the app's log.
        log = self.home / '.local/state/ominx/forge/org.example.greeter.log'
        for _ in range(100):
            if log.exists() and 'Hello, OminX!' in log.read_text():
                break
            time.sleep(0.05)
        self.assertEqual(log.read_text(), 'Hello, OminX!\n')
        self.assertEqual(oct(log.stat().st_mode & 0o777), '0o644')

    def test_validator_accepts_forge_and_refuses_bad_entries(self):
        proj = self.root / 'proj'
        self.forge('new', str(proj), '--id', 'org.example.v', '--name', 'V')
        self.forge('build', str(proj))
        pkg = proj / 'build/org.example.v-1.0.0.opkgx'
        r = subprocess.run([OPKGX, 'validate', str(pkg)], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_forge_entry_must_be_a_fg_file(self):
        stage = self.root / 'stage'
        (stage / 'app').mkdir(parents=True)
        (stage / 'opkgx.manifest').write_text('format=1\nid=org.example.bad\nname=Bad\nversion=1.0.0\n'
                                              'arch=x86_64\nrunner=forge\nexec=app/run.sh\n')
        (stage / 'app/run.sh').write_text('#!/bin/sh\n')
        r = subprocess.run([OPKGX, 'pack', str(stage), str(self.root / 'bad.opkgx')],
                           capture_output=True, text=True, timeout=30)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('exec-not-forge', r.stderr)


if __name__ == '__main__':
    unittest.main()
