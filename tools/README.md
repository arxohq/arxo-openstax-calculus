The ordinary reader commands are native `law eval` and `law inspect` in the main README.

`solve.py` / `input_syntax.py` are a syntax-to-lawcase adapter. They serialize literal
numbers, AST nodes and a fixed finite carrier inventory. They contain no calculus
formula, method-selection loop, polynomial simplifier or answer table. Native
`law engine lower-ask` compiles the case, and `law eval` computes every query.

`check.py` replays the shipped canonical documents twice and checks the selected
native suites. `measure_depth.py` calls the existing shared classifier in `depth/`
against exact original source modules and package-own CLIR. `canon_publication.py`
is the existing allowlisted export/inventory tool. No full corpus is discovered.
