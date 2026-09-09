extends Node

# --- forms the lift carries ---------------------------------------------------

func add_two(a: int, b: int) -> int:
	return a + b

func precedence(a: int, b: int, c: int) -> int:
	return a + b * c

func parens(a: int, b: int, c: int) -> int:
	return (a + b) * c

func comparison(a: int, b: int) -> bool:
	return a < b

func boolean(a: bool, b: bool) -> bool:
	return a and b or not a

func ternary_form(a: int, b: int) -> int:
	return a if a > b else b

func clamp_form(a: float, lo: float, hi: float) -> float:
	return clampf(a, lo, hi)

func min_max(a: int, b: int) -> int:
	return maxi(mini(a, b), a)

func local_var(a: int, b: int) -> int:
	var c = a * b
	return c + a

func typed_local(a: int, b: int) -> float:
	var c: float = a + b
	return c

func compound(a: int, b: int) -> int:
	var c = a
	c += b
	c *= 2
	return c

func if_else(a: int, b: int) -> int:
	var c = 0
	if a > b:
		c = a
	else:
		c = b
	return c

func if_no_else(a: int, b: int) -> int:
	var c = b
	if a > b:
		c = a
	return c

func passthrough(a: int) -> int:
	return a

func negation(a: int) -> int:
	return -a

func real_literal(a: float) -> float:
	return a * 1.5

func exponent_literal(a: float) -> float:
	return a * 1.5e-3

func modulo(a: int, b: int) -> int:
	return a % b

func nested_ternary(a: int, b: int, c: int) -> int:
	return a if a > b else b if b > c else c

func shared_local(a: int, b: int) -> int:
	var c = a * b
	return c + c

# --- forms the lift refuses, one reason each ----------------------------------

func no_return_type(a: int):
	return a

func void_return(a: int) -> void:
	return a

func bad_return_type(a: int) -> String:
	return a

func no_parameters() -> int:
	return 1

func bad_parameter_type(a: String) -> int:
	return 1

func for_loop(a: int) -> int:
	for i in range(3):
		a += 1
	return a

func while_loop(a: int) -> int:
	while a < 3:
		a += 1
	return a

func match_statement(a: int) -> int:
	match a:
		1:
			a = 2
	return a

func member_access(a: int) -> int:
	return a.x

func array_index(a: int) -> int:
	return a[0]

func string_literal(a: int) -> int:
	var s = "hello"
	return a

func conversion_call(a: int) -> float:
	return float(a)

func abs_call(a: int) -> int:
	return abs(a)

func unknown_call(a: int) -> int:
	return sqrt(a)

func elif_branch(a: int, b: int) -> int:
	var c = 0
	if a > b:
		c = a
	elif a < b:
		c = b
	return c

func return_in_branch(a: int, b: int) -> int:
	if a > b:
		return a
	return b

func statements_after_return(a: int) -> int:
	return a
	a = 1

func return_without_value(a: int) -> int:
	return

func var_without_value(a: int) -> int:
	var c
	return a

func bad_local_type(a: int) -> int:
	var c: String = a
	return c

func unknown_name(a: int) -> int:
	return a + z

func returns_constant(a: int) -> int:
	return 1

func ternary_without_else(a: int, b: int) -> int:
	return a if a > b

func unbalanced_paren(a: int, b: int) -> int:
	return (a + b

func trailing_tokens(a: int, b: int) -> int:
	return a b

func clamp_arity(a: float, b: float) -> float:
	return clampf(a, b)

func member_assignment(a: int) -> int:
	self.x = a
	return a

func udon_hook(a: int) -> int:
	return a

func _private_hook(a: int) -> int:
	return a
