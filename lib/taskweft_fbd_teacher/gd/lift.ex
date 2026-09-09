defmodule TaskweftFbdTeacher.Gd.Lift do
  @moduledoc """
  The lift from a translated method back to a diagram: the straight-line SafeGDScript
  subset a scan controller can carry, refused by reason beyond it.

  A method `func Name(p: T, ...) -> R:` whose body is local assignments, arithmetic,
  comparison and boolean expressions, `clampi/clampf/mini/minf/maxi/maxf`, an `if`/`else`
  whose branches assign values, and a `return`, lifts to a scan program: one `in` per
  parameter, `out ret` for the return, one block per operation.

  Tokenising and statement shapes are read by splitting rather than by pattern, so this
  module carries no Regex and passes the parse-not-regex ruling.
  """

  @types %{"int" => "INT", "float" => "REAL", "bool" => "BOOL"}
  @bin %{"+" => "ADD", "-" => "SUB", "*" => "MUL", "/" => "DIV", "%" => "MOD",
         "==" => "EQ", "!=" => "NE", "<" => "LT", ">" => "GT", "<=" => "LE", ">=" => "GE",
         "and" => "AND", "or" => "OR"}
  @calls %{"clampi" => "LIMIT", "clampf" => "LIMIT", "mini" => "MIN", "minf" => "MIN",
           "maxi" => "MAX", "maxf" => "MAX", "min" => "MIN", "max" => "MAX", "clamp" => "LIMIT"}
  @prec %{"or" => 1, "and" => 2, "==" => 4, "!=" => 4, "<" => 4, ">" => 4, "<=" => 4,
          ">=" => 4, "+" => 5, "-" => 5, "*" => 6, "/" => 6, "%" => 6}

  @two ~w(== != <= >= += -= *= /=)
  @one ~c"-+*/%<>=(),:.[]"
  @digits ~c"0123456789"
  @alpha ~c"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_"
  @alnum @alpha ++ @digits

  defmodule Method do
    @moduledoc false
    defstruct [:name, :params, :ret, :body]
  end

  defp refuse(reason), do: throw({:refused, reason})

  # The refusal wording is contract, and the reference quotes with Python's repr.
  defp repr(s), do: "'" <> s <> "'"

  # --- tokens ---------------------------------------------------------------------

  def tokenize(line), do: toks(line, [])

  defp toks("", acc), do: Enum.reverse(acc)

  defp toks(<<c::utf8, rest::binary>> = s, acc) do
    cond do
      c in [?\s, ?\t] ->
        toks(rest, acc)

      c in @digits ->
        {tok, tail} = number(s)
        toks(tail, [tok | acc])

      c in @alpha ->
        {tok, tail} = span(s, @alnum)
        toks(tail, [tok | acc])

      c == ?" ->
        case String.split(rest, "\"", parts: 2) do
          [body, tail] -> toks(tail, ["\"" <> body <> "\"" | acc])
          _ -> refuse("token: #{repr(String.slice(s, 0, 10))}")
        end

      true ->
        two = String.slice(s, 0, 2)

        cond do
          two in @two -> toks(String.slice(s, 2..-1//1), [two | acc])
          c in @one -> toks(rest, [<<c::utf8>> | acc])
          String.trim(s) == "" -> Enum.reverse(acc)
          true -> refuse("token: #{repr(String.slice(s, 0, 10))}")
        end
    end
  end

  defp span(s, set) do
    {t, tail} = s |> String.to_charlist() |> Enum.split_while(&(&1 in set))
    {List.to_string(t), List.to_string(tail)}
  end

  # `12.`, `12.5`, `12.5e-3` and `12` are the forms; an exponent needs the dot, as in the
  # pattern this replaces, so `1e5` tokenises as `1` then `e5`.
  defp number(s) do
    {int, tail} = span(s, @digits)

    case tail do
      <<?., rest::binary>> ->
        {frac, tail2} = span(rest, @digits)
        {exp, tail3} = exponent(tail2)
        {int <> "." <> frac <> exp, tail3}

      _ ->
        {int, tail}
    end
  end

  defp exponent(<<?e, rest::binary>> = s) do
    {sign, rest2} =
      case rest do
        <<c::utf8, r::binary>> when c in [?-, ?+] -> {<<c::utf8>>, r}
        _ -> {"", rest}
      end

    {digits, tail} = span(rest2, @digits)
    if digits == "", do: {"", s}, else: {"e" <> sign <> digits, tail}
  end

  defp exponent(s), do: {"", s}

  # --- expressions ----------------------------------------------------------------

  def parse_expr(text) do
    {e, rest} = ternary(tokenize(text))
    if rest != [], do: refuse("expression: trailing #{repr(hd(rest))}")
    e
  end

  defp ternary(toks) do
    {e, rest} = binary_expr(toks, 1)

    case rest do
      ["if" | r] ->
        {c, r2} = binary_expr(r, 1)

        case r2 do
          ["else" | r3] ->
            {o, r4} = ternary(r3)
            {{:cond, c, e, o}, r4}

          _ ->
            refuse("expression: ternary without else")
        end

      _ ->
        {e, rest}
    end
  end

  defp binary_expr(toks, minp) do
    {left, rest} = unary(toks)
    climb(left, rest, minp)
  end

  defp climb(left, [op | rest], minp) when is_map_key(@prec, op) do
    if @prec[op] >= minp do
      {right, rest2} = binary_expr(rest, @prec[op] + 1)
      climb({:op, @bin[op], [left, right]}, rest2, minp)
    else
      {left, [op | rest]}
    end
  end

  defp climb(left, rest, _minp), do: {left, rest}

  defp unary(["not" | rest]) do
    {e, r} = unary(rest)
    {{:op, "NOT", [e]}, r}
  end

  defp unary(["-" | rest]) do
    case unary(rest) do
      {{:lit, v, t}, r} -> {{:lit, "-" <> v, t}, r}
      {e, r} -> {{:op, "SUB", [{:lit, "0", "INT"}, e]}, r}
    end
  end

  defp unary(toks), do: primary(toks)

  defp primary([]), do: refuse("expression: ended early")

  defp primary(["(" | rest]) do
    {e, r} = ternary(rest)

    case r do
      [")" | r2] -> {e, r2}
      _ -> refuse("expression: unbalanced parenthesis")
    end
  end

  defp primary([p | rest]) do
    cond do
      real_literal?(p) -> {{:lit, if(String.ends_with?(p, "."), do: p <> "0", else: p), "REAL"}, rest}
      int_literal?(p) -> {{:lit, p, "INT"}, rest}
      p in ["true", "false"] -> {{:lit, String.upcase(p), "BOOL"}, rest}
      String.starts_with?(p, "\"") -> refuse("string literal")
      name?(p) -> named(p, rest)
      true -> refuse("expression: #{repr(p)}")
    end
  end

  defp named(p, ["(" | rest]) do
    {args, r} = arguments(rest, [])

    cond do
      p in ["float", "int"] -> refuse("call: #{p}() conversion")
      p in ["absf", "absi", "abs"] -> refuse("call: abs (no ABS block)")
      not is_map_key(@calls, p) -> refuse("call: #{p}")
      true -> {{:op, @calls[p], args}, r}
    end
  end

  defp named(p, ["." | rest]), do: refuse("member access: #{p}.#{List.first(rest) || ""}")
  defp named(_p, ["[" | _rest]), do: refuse("array index")
  defp named(p, rest), do: {{:var, p}, rest}

  defp arguments([")" | rest], acc), do: {Enum.reverse(acc), rest}

  defp arguments(toks, acc) do
    {e, rest} = ternary(toks)

    case rest do
      ["," | r] -> arguments(r, [e | acc])
      _ -> arguments(rest, [e | acc])
    end
  end

  defp int_literal?(s), do: s != "" and all_in?(s, @digits)

  defp real_literal?(s) do
    case String.split(s, ".", parts: 2) do
      [i, f] -> all_in?(i, @digits) and i != "" and fraction?(f)
      _ -> false
    end
  end

  defp fraction?(f) do
    case String.split(f, "e", parts: 2) do
      [d] -> all_in?(d, @digits)
      [d, e] -> all_in?(d, @digits) and signed_digits?(e)
    end
  end

  defp signed_digits?(<<c::utf8, r::binary>>) when c in [?-, ?+], do: r != "" and all_in?(r, @digits)
  defp signed_digits?(s), do: s != "" and all_in?(s, @digits)

  defp name?(s) do
    case String.to_charlist(s) do
      [h | t] -> h in @alpha and Enum.all?(t, &(&1 in @alnum))
      [] -> false
    end
  end

  defp all_in?(s, set), do: s |> String.to_charlist() |> Enum.all?(&(&1 in set))

  # --- methods --------------------------------------------------------------------

  def methods_of(text) do
    text |> String.split("\n") |> Enum.map(&String.trim_trailing(&1, "\r")) |> collect([])
  end

  defp collect([], acc), do: Enum.reverse(acc)

  defp collect([line | rest], acc) do
    case func_header(line) do
      nil ->
        collect(rest, acc)

      {name, params, ret} ->
        {body, tail} = take_body(rest, [])
        collect(tail, [%Method{name: name, params: params, ret: ret, body: body} | acc])
    end
  end

  # `func Name(a: int, b := 2) -> int:` with the trailing colon required.
  defp func_header(line) do
    with true <- String.starts_with?(line, "func "),
         true <- String.ends_with?(String.trim_trailing(line), ":"),
         rest <- line |> String.trim_trailing() |> String.trim_trailing(":"),
         [name, after_name] <- String.split(String.slice(rest, 5..-1//1), "(", parts: 2),
         true <- name?(name),
         [inside, after_paren] <- rsplit_paren(after_name) do
      ret =
        case String.trim(after_paren) do
          "" -> nil
          "-> " <> r -> String.trim(r)
          "->" <> r -> String.trim(r)
          _ -> nil
        end

      {name, params_of(inside), ret}
    else
      _ -> nil
    end
  end

  defp rsplit_paren(s) do
    case String.split(s, ")") do
      [_] -> nil
      parts -> [Enum.join(Enum.drop(parts, -1), ")"), List.last(parts)]
    end
  end

  defp params_of(inside) do
    inside
    |> String.split(",")
    |> Enum.map(&String.trim/1)
    |> Enum.reject(&(&1 == ""))
    |> Enum.map(fn p ->
      case String.split(p, ":", parts: 2) do
        [only] -> {only |> String.split("=") |> hd() |> String.trim(), "?"}
        [n, t] -> {String.trim(n), t |> String.split("=") |> hd() |> String.trim()}
      end
    end)
  end

  defp take_body([], acc), do: {Enum.reverse(acc), []}

  defp take_body([line | rest] = all, acc) do
    cond do
      String.starts_with?(line, "\t") -> take_body(rest, [line | acc])
      String.trim(line) == "" -> take_body(rest, acc)
      true -> {Enum.reverse(acc), all}
    end
  end

  # --- the lifter -----------------------------------------------------------------

  defmodule S do
    @moduledoc false
    defstruct lines: [], types: %{}, values: %{}, counter: 0
  end

  defp fresh(s), do: {%{s | counter: s.counter + 1}, "b#{s.counter + 1}"}

  defp type_of({:wire, _t, ty}, _s), do: ty
  defp type_of({:lit, _v, t}, _s), do: t

  defp type_of({:var, n}, s) do
    Map.get(s.types, n) || refuse("unknown name: #{n}")
  end

  defp type_of({:cond, _c, t, _o}, s), do: type_of(t, s)

  defp type_of({:op, kind, args}, s) do
    if kind in ~w(EQ NE LT GT LE GE AND OR NOT) do
      "BOOL"
    else
      ts = Enum.map(args, &type_of(&1, s))
      if "REAL" in ts, do: "REAL", else: hd(ts)
    end
  end

  defp operand({:wire, text, _t}, s), do: {s, text}
  defp operand({:lit, v, _t}, s), do: {s, v}

  defp operand({:var, n}, s) do
    cond do
      Map.has_key?(s.values, n) -> operand(s.values[n], s)
      Map.has_key?(s.types, n) -> {s, n}
      true -> refuse("unknown name: #{n}")
    end
  end

  defp operand(e, s), do: emit(e, s)

  # The number is taken before the operands are evaluated, so a nested block numbers
  # after the one that reads it while still being emitted above it.
  defp emit({:cond, test, then_e, other}, s) do
    {s, b} = fresh(s)
    {s, g} = operand(test, s)
    {s, in0} = operand(other, s)
    {s, in1} = operand(then_e, s)
    {%{s | lines: s.lines ++ ["#{b} = SEL(G=#{g}, IN0=#{in0}, IN1=#{in1})"]}, "#{b}.OUT"}
  end

  defp emit({:op, "NOT", [a]}, s) do
    {s, b} = fresh(s)
    {s, x} = operand(a, s)
    {%{s | lines: s.lines ++ ["#{b} = NOT(IN=#{x})"]}, "#{b}.OUT"}
  end

  defp emit({:op, "LIMIT", args}, s) do
    if length(args) != 3, do: refuse("clamp arity")
    [a, lo, hi] = args
    {s, b} = fresh(s)
    {s, vlo} = operand(lo, s)
    {s, va} = operand(a, s)
    {s, vhi} = operand(hi, s)
    {%{s | lines: s.lines ++ ["#{b} = LIMIT(MN=#{vlo}, IN=#{va}, MX=#{vhi})"]}, "#{b}.OUT"}
  end

  defp emit({:op, kind, args}, s) do
    {s, ins} =
      Enum.reduce(args, {s, []}, fn a, {acc, out} ->
        {acc2, v} = operand(a, acc)
        {acc2, out ++ [v]}
      end)

    variadic = kind in ~w(ADD MUL MIN MAX AND OR) and length(ins) > 2
    if not variadic and length(ins) != 2, do: refuse("#{kind} arity #{length(ins)}")
    {s, b} = fresh(s)
    pins = ins |> Enum.with_index(1) |> Enum.map_join(", ", fn {v, i} -> "IN#{i}=#{v}" end)
    {%{s | lines: s.lines ++ ["#{b} = #{kind}(#{pins})"]}, "#{b}.OUT"}
  end

  defp assign(s, name, e) do
    t = type_of(e, s)
    prior = Map.get(s.types, name)

    if prior != nil and prior != t and not (prior == "REAL" and t == "INT"),
      do: refuse("assignment changes the type of #{name}")

    s = %{s | types: Map.put_new(s.types, name, t)}

    case e do
      {tag, _, _} when tag in [:op, :cond] ->
        {s, text} = emit(e, s)
        %{s | values: Map.put(s.values, name, {:wire, text, s.types[name]})}

      _ ->
        %{s | values: Map.put(s.values, name, e)}
    end
  end

  # --- statements -----------------------------------------------------------------

  defp block(s, lines, depth), do: step(s, lines, depth)

  defp step(s, [], _depth), do: {s, nil}

  defp step(s, [raw | rest], depth) do
    ind = indent_of(raw)
    if ind != depth, do: refuse("indentation")
    line = String.trim(raw)

    cond do
      String.starts_with?(line, "#") ->
        step(s, rest, depth)

      String.starts_with?(line, "for ") or String.starts_with?(line, "while ") ->
        refuse(hd(String.split(line)) <> " loop")

      String.starts_with?(line, "match ") ->
        refuse("match")

      String.starts_with?(line, "var ") or String.starts_with?(line, "const ") ->
        step(declaration(s, line), rest, depth)

      String.starts_with?(line, "return") ->
        rest_text = line |> String.slice(6..-1//1) |> String.trim()
        if rest_text == "", do: refuse("return without a value")
        if rest != [], do: refuse("statements after return")
        {s2, text} = operand(parse_expr(rest_text), s)
        {s2, text}

      String.starts_with?(line, "if ") ->
        cond_e = line |> String.slice(3..-1//1) |> String.trim_trailing(":") |> parse_expr()
        {then_lines, rest2} = deeper(rest, depth, [])

        {else_lines, rest3} =
          case rest2 do
            [l | r] ->
              cond do
                String.trim(l) == "else:" -> deeper(r, depth, [])
                String.starts_with?(String.trim(l), "elif ") -> refuse("elif")
                true -> {[], rest2}
              end

            [] ->
              {[], rest2}
          end

        step(branch(s, cond_e, then_lines, else_lines, depth + 1), rest3, depth)

      true ->
        step(assignment(s, line), rest, depth)
    end
  end

  defp indent_of(raw) do
    raw |> String.to_charlist() |> Enum.take_while(&(&1 == ?\t)) |> length()
  end

  defp deeper([l | r], depth, acc) do
    if String.trim(l) != "" and indent_of(l) > depth,
      do: deeper(r, depth, [l | acc]),
      else: {Enum.reverse(acc), [l | r]}
  end

  defp deeper([], _depth, acc), do: {Enum.reverse(acc), []}

  defp declaration(s, line) do
    body = line |> String.split(" ", parts: 2) |> Enum.at(1, "")

    case String.split(body, "=", parts: 2) do
      [lhs, rhs] ->
        {name, declared} =
          case String.split(lhs, ":", parts: 2) do
            [n] -> {String.trim(n), nil}
            [n, t] -> {String.trim(n), String.trim(t)}
          end

        if declared != nil and not is_map_key(@types, declared), do: refuse("type: #{declared}")
        if not name?(name), do: refuse("var without a value")
        s = assign(s, name, parse_expr(String.trim(rhs)))
        if declared, do: %{s | types: Map.put(s.types, name, @types[declared])}, else: s

      _ ->
        refuse("var without a value")
    end
  end

  defp assignment(s, line) do
    case split_assign(line) do
      nil ->
        if String.contains?(line, "(") and String.ends_with?(line, ")") or String.contains?(line, "."),
          do: refuse("call statement: #{line |> String.split("(") |> hd()}"),
          else: refuse("statement: #{String.slice(line, 0, 20)}")

      {name, op, rhs} ->
        if String.contains?(name, ".") or String.contains?(name, "["),
          do: refuse("member assignment")

        e = parse_expr(rhs)

        e =
          if op == "=" do
            e
          else
            if not Map.has_key?(s.types, name), do: refuse("unknown name: #{name}")
            left = Map.get(s.values, name) || {:var, name}
            {:op, @bin[String.first(op)], [left, e]}
          end

        assign(s, name, e)
    end
  end

  # `name op rhs` where op is one of the compound forms or a bare `=`.
  defp split_assign(line) do
    Enum.find_value(["+=", "-=", "*=", "/="], fn op ->
      case String.split(line, op, parts: 2) do
        [l, r] -> if name?(String.trim(l)), do: {String.trim(l), op, String.trim(r)}, else: nil
        _ -> nil
      end
    end) ||
      case String.split(line, "=", parts: 2) do
        [l, r] ->
          if name?(String.trim(l)) and not String.starts_with?(r, "="),
            do: {String.trim(l), "=", String.trim(r)},
            else: nil

        _ ->
          nil
      end
  end

  defp branch(s, cond_e, then_lines, else_lines, depth) do
    {s, cond_wire} = operand(cond_e, s)
    before = s.values

    for arm <- [then_lines, else_lines], raw <- arm do
      line = String.trim(raw)
      if String.starts_with?(line, "return"), do: refuse("return inside a branch")

      if split_assign(line) == nil or String.starts_with?(line, "if ") or
           String.starts_with?(line, "var "),
         do: refuse("branch is not an assignment")
    end

    {then_s, _} = block(%{s | values: before}, then_lines, depth)

    {else_s, _} =
      if else_lines == [],
        do: {%{then_s | values: before, types: s.types}, nil},
        else: block(%{then_s | values: before, types: s.types}, else_lines, depth)

    names = (Map.keys(then_s.values) ++ Map.keys(else_s.values)) |> Enum.uniq() |> Enum.sort()
    s = %{s | lines: else_s.lines, counter: else_s.counter}

    Enum.reduce(names, s, fn n, acc ->
      a = Map.get(then_s.values, n, Map.get(before, n))
      b = Map.get(else_s.values, n, Map.get(before, n))

      cond do
        a == nil or b == nil ->
          refuse("#{n} is assigned in one branch and undefined before the if")

        a == b ->
          acc

        true ->
          ty = Map.get(acc.types, n) || Map.get(then_s.types, n) || Map.get(else_s.types, n)
          acc = %{acc | types: Map.put_new(acc.types, n, ty)}
          {acc, in0} = operand(b, acc)
          {acc, in1} = operand(a, acc)
          {acc, sel} = fresh(acc)

          %{
            acc
            | lines: acc.lines ++ ["#{sel} = SEL(G=#{cond_wire}, IN0=#{in0}, IN1=#{in1})"],
              values: Map.put(acc.values, n, {:wire, "#{sel}.OUT", ty})
          }
      end
    end)
  end

  # --- the entry points -----------------------------------------------------------

  def lift_method(%Method{} = m, program \\ nil) do
    if m.ret in [nil, "void"], do: refuse("void method")
    if not is_map_key(@types, m.ret), do: refuse("return type: #{m.ret}")
    if m.params == [], do: refuse("no parameters")

    types =
      Map.new(m.params, fn {n, t} ->
        if not is_map_key(@types, t), do: refuse("parameter type: #{t}")
        {n, @types[t]}
      end)

    {s, ret} = block(%S{types: types}, m.body, 1)
    if ret == nil, do: refuse("no return")
    if s.lines == [] and not name?(ret), do: refuse("returns a constant")

    param_names = Enum.map(m.params, &elem(&1, 0))

    if name?(ret) and Map.has_key?(s.types, ret) and ret not in param_names,
      do: refuse("returns a local never assigned")

    {s, ret} =
      if name?(ret) and ret in param_names do
        {s2, b} = fresh(s)
        {%{s2 | lines: s2.lines ++ ["#{b} = MOVE(IN=#{ret})"]}, "#{b}.OUT"}
      else
        {s, ret}
      end

    head =
      ["program #{program || m.name}"] ++
        Enum.map(m.params, fn {n, t} -> "in #{n} : #{@types[t]}" end) ++
        ["out ret : #{@types[m.ret]}"]

    Enum.join(head ++ s.lines ++ ["ret = #{ret}"], "\n") <> "\n"
  end

  @doc "Every method of a translated class: lifted text by name, and refusals by name."
  def lift_all(text) do
    Enum.reduce(methods_of(text), {%{}, %{}}, fn m, {lifted, refused} ->
      if String.starts_with?(m.name, "udon_") or String.starts_with?(m.name, "_") do
        {lifted, Map.put(refused, m.name, "runtime hook")}
      else
        case safely(fn -> lift_method(m) end) do
          {:ok, text} -> {Map.put(lifted, m.name, text), refused}
          {:refused, why} -> {lifted, Map.put(refused, m.name, why)}
        end
      end
    end)
  end

  def safely(fun) do
    {:ok, fun.()}
  catch
    {:refused, why} -> {:refused, why}
  end
end
