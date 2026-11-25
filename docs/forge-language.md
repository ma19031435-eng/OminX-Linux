# Forge language, version 1.0

Forge is the language for apps on OminXOS. It is small, dynamically typed, and
runs on an interpreter built into `ominx-forge`. A Forge app is a folder of
`.fg` files, packaged as an `.opkgx` (see `docs/opkgx-system.md`) and written in
Forge Studio (see `docs/forge-studio.md`).

Forge runs only on OminXOS. The shipped `ominx-forge` refuses to run anywhere
else, with exit status 3. That is a product gate, not a security boundary: it
keeps Forge tied to the platform, and confinement comes from the program model
below.

This document is the language reference. The implementation is
`src/forge/forge.c` (front end, checker, interpreter) with `src/forge/forge.h`
for the limits.

## A first program

```
// A program starts at main().
fn main() {
    let names = ["Ada", "Grace", "Linus"]
    for name in names {
        print("Hello, " + name + "!")
    }
}
```

## Lexical rules

- Source is UTF-8 text, at most 1 MiB per file.
- Statements end at a line break. There are no semicolons.
- Comments start with `//` and run to the end of the line.
- Identifiers start with a letter or `_`, then letters, digits or `_`.
- Keywords: `let fn if else while for in return break continue true false nil and or not import`.
- Integer literals are decimal digits. Float literals have a `.` with digits on
  both sides, for example `2.5` or `0.25`. Exponents are not supported.
- String literals use double quotes. Escapes: `\n`, `\t`, `\r`, `\"`, `\\`, `\0`.
  Any other escape is an error.
- A string holds bytes. Source text is read as UTF-8, and the bytes are kept as
  they are.

## Values and types

| Type | Examples | Notes |
|---|---|---|
| `nil` | `nil` | the only value of type nil |
| `bool` | `true`, `false` | conditions must be `bool`; there is no truthiness |
| `int` | `42`, `-7` | 64-bit signed. Overflow is an error |
| `float` | `2.5`, `1.0` | 64-bit IEEE. Mixed `int`/`float` arithmetic gives a `float` |
| `str` | `"hi"` | a byte string |
| `list` | `[1, "a", nil]` | ordered, growable, mixed types allowed |
| `map` | `{"a": 1}` | keys are strings; insertion order is kept |
| `fn` | `fn(x) { return x }` | functions, closures and builtins |

`type(v)` returns the type name as a string: `"nil"`, `"bool"`, `"int"`,
`"float"`, `"str"`, `"list"`, `"map"` or `"fn"`.

## Operators

From lowest to highest precedence:

| Level | Operators | Rule |
|---|---|---|
| 1 | `or` | both sides must be `bool`; the right side runs only when the left is `false` |
| 2 | `and` | both sides must be `bool`; the right side runs only when the left is `true` |
| 3 | `not` | prefix; operand must be `bool` |
| 4 | `==` `!=` | equality, see below. Never an error |
| 5 | `<` `<=` `>` `>=` | numbers compare as numbers, strings compare as bytes; anything else is an error |
| 6 | `+` `-` | numbers; `+` also joins two strings and two lists |
| 7 | `*` `/` `%` | numbers. `/` and `%` on two ints truncate toward zero. `%` needs two ints |
| 8 | unary `-` | numbers |
| 9 | call `f(...)`, index `x[i]` | postfix |

`not a == b` means `not (a == b)`, because `not` is lower than `==`.

Arithmetic examples:

```
print(7 / 2)        // 3      (int division truncates)
print(7.0 / 2)      // 3.5
print(-7 % 3)       // -1     (remainder takes the sign of the dividend)
print(1 + 2 * 3)    // 7
```

### Equality

- Numbers: `1 == 1.0` is `true`.
- Strings compare by content. Lists compare element by element. Maps compare
  key by key, and key order does not matter.
- Values of different types are never equal, except int and float as above.
- Functions and builtins compare by identity.
- Cyclic lists or maps are compared to a fixed depth of 64. Past that depth they
  count as unequal.

## Statements

```
let x = 1                 // declare
x = x + 1                 // assign (the name must already be declared)
xs[0] = 9                 // assign into a list
m["key"] = "value"        // assign into a map
if x > 1 { ... } else if x == 1 { ... } else { ... }
while x < 10 { x = x + 1 }
for item in xs { ... }    // list items, string bytes, or map keys
for i in range(5) { ... } // 0 to 4
break                     // leave the innermost loop
continue                  // next iteration of the innermost loop
return value              // leave the function with a value
return                    // leave with nil; the value must be on the same line
```

`return` takes its value only when the value starts on the same line. A bare
`return` followed by a new line returns `nil`.

Loops over a string give one-byte strings. Loops over a map give its keys.

## Functions and closures

```
fn add(a, b) {
    return a + b
}

fn make_counter() {
    let n = 0
    return fn() {          // anonymous function; it captures n
        n = n + 1
        return n
    }
}

fn main() {
    let next = make_counter()
    next()
    print(next())          // 2
    print(add(2, 3))       // 5
}
```

- Functions can be used before the line where they are written. Top-level
  functions are known throughout the program.
- Parameters are local to the call. Assigning to a parameter does not change the
  caller's value.
- A closure keeps the variables it uses, so the counter above keeps its state.
- Call depth is limited to 400. Deeper recursion is a runtime error, not a crash.

## Scope

- A block (`{ ... }`) has its own scope. A name declared in a block is gone when
  the block ends.
- An inner scope may declare a name that an outer scope also declares; the inner
  one hides it.
- Declaring the same name twice in one scope is an error.
- The body of a function is its own scope inside the call. A `let` in the body
  may reuse a parameter's name; the new variable hides the parameter from that
  point on.
- `for` variables belong to their loop.
- At the top of a file only `let`, `fn` and `import` are allowed. Functions are
  available from the start of the program. Top-level `let` values are computed in
  file order, so a top-level `let` can use functions and earlier `let`s. Using a
  `let` that appears later is a runtime error, reported at the place of use.

## Builtins

Builtins are names that user code cannot redefine at the top level. A local
variable may use one of these names and hide it inside its own scope.

| Builtin | Arguments | Result |
|---|---|---|
| `print(...)` | any number | prints the values separated by spaces, then a newline |
| `len(x)` | string, list or map | length. Strings count bytes |
| `str(x)` | any | the display form as a string |
| `int(x)` | int, float, bool or string | `int`. A float truncates. A string must be a whole integer |
| `float(x)` | int, float or string | `float` |
| `type(x)` | any | the type name |
| `push(list, x)` | list, any | appends `x`; returns `nil` |
| `pop(list)` | list | removes and returns the last item. The list must not be empty |
| `keys(map)` | map | list of keys, in insertion order |
| `has(map, key)` | map, string | `bool` |
| `remove(map, key)` | map, string | removes the key; returns `true` if it was there |
| `split(s, sep)` | string, string | list of strings. An empty separator is an error |
| `join(list, sep)` | list, string | joins the display form of each item |
| `upper(s)`, `lower(s)` | string | ASCII letters only |
| `trim(s)` | string | removes leading and trailing whitespace |
| `contains(x, y)` | string and string, or list and any | `bool` |
| `starts_with(s, p)`, `ends_with(s, p)` | string, string | `bool` |
| `replace(s, old, new)` | string, string, string | replaces every match. `old` must not be empty |
| `substr(s, start, count)` | string, int, int | `count` bytes from `start`. Out of range is an error |
| `abs(n)` | int or float | absolute value |
| `min(a, b)`, `max(a, b)` | two numbers | the smaller or larger |
| `floor(x)` | int or float | the largest integer not above `x`, as an `int` |
| `sqrt(x)` | int or float | `float`. A negative value is an error |
| `range(n)` | int from 0 to 1000000 | list `[0, ..., n-1]` |
| `read_asset(name)` | string | the text of a file in the app's `assets/` folder |
| `assert(cond)`, `assert(cond, msg)` | bool, optional string | stops with `assertion failed` if `cond` is false |
| `error(msg)` | string | stops the program with `msg` |
| `exit(code)` | int | ends the program with `code & 255`. Exit status is the code |

Indexing: `xs[i]` for lists and `s[i]` for strings. `i` must be an int in range.
Negative indexes are errors. `m[key]` for maps; a missing key is an error, so
check with `has` first.

Strings and `len` count bytes. `upper` and `lower` change ASCII letters only.
Use these rules when text may contain non-ASCII characters.

## Imports

```
import "lib/geometry.fg"
```

- The path is relative to the importing file. It must stay inside the project:
  no leading `/`, no `..`, no backslashes.
- Imported declarations and the importing file's declarations share one global
  namespace. A name may be declared only once across all of them.
- Import cycles are an error.
- `import` is allowed only at the top of a file.

## Tests

A file may define test functions named `test_*`. `ominx-forge test` runs each one
and reports `ok` or `FAIL` with the failing line. A test that passes returns
normally. `assert` in a test fails it.

```
fn test_doubles() {
    assert(double(4) == 8, "double is broken")
}
```

## Errors and diagnostics

Each file is checked before it runs. Problems are reported as `file:line:col`:

```
src/main.fg:3:12: error: undefined name 'totl'
```

Checked before running:

- undefined names; assignment to an undeclared name
- duplicate declarations in one scope, duplicate top-level names, duplicate parameters
- `break` or `continue` outside a loop; top-level statements other than `let`, `fn` and `import`
- builtin argument counts, and user function argument counts when the function is known
- builtin names redefined at the top level
- parse errors, unterminated strings, unknown escapes, unexpected characters
- import problems: missing files, cycles, paths outside the project

Found at runtime, with the line and column of the failing expression:

- division or remainder by zero
- index out of range, missing map key
- condition or operand of the wrong type
- integer overflow
- failed conversions (`int("x")`)
- calling a non-function, or a wrong argument count for a value only known at runtime
- stack depth over 400 calls
- `assert` and `error`

## Limits

| Limit | Value |
|---|---|
| Source file size | 1 MiB |
| Files in one program | 256 |
| Diagnostics printed | 64 |
| Call depth | 400 |
| Heap (all values) | 256 MiB |
| Output (`print`) | 16 MiB |
| Nesting of expressions and blocks | 200 levels |
| `range` size | 1000000 |

Hitting a limit stops the program with a clear message. Forge does not crash
or run unbounded. Memory is released when the program exits.

## Known semantics

- `%` follows C truncation: `-7 % 3` is `-1`. `%` needs two ints.
- `/` on two ints truncates toward zero: `-7 / 2` is `-3`.
- Strings are bytes: `len("héllo")` is 6.
- Printing a list or map that contains itself shows `...` where the cycle would
  repeat.
- There is no exponent notation, no `null`, no classes and no exceptions.
  Errors stop the program.

## Versioning

This is Forge 1.0. Programs written for 1.0 keep working on later 1.x releases.
Breaking changes need a new major version.
