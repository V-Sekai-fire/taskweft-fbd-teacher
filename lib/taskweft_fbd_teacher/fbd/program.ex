defmodule TaskweftFbdTeacher.Fbd.Program do
  @moduledoc """
  The compiler's text form as a struct, with a printer and the mutations as
  struct edits. Nothing here parses the text form or a signature table; every
  read of either goes through the compiler's JSON modes.
  """

  alias __MODULE__, as: Program

  defmodule Block do
    @moduledoc "One assignment line: `id = KIND(pin=value, ...)` or `id = CALL[Class.method](...)`."
    defstruct [:id, :kind, :sig, pins: []]
  end

  defstruct [:name, ins: [], outs: [], vars: [], blocks: [], writes: []]

  @type value ::
          {:ref, String.t(), String.t()}
          | {:var, String.t()}
          | {:int, integer()}
          | {:real, float()}
          | {:bool, boolean()}
          | {:time_ms, non_neg_integer()}
          | {:string, String.t()}
          | {:code, String.t(), [non_neg_integer()]}

  @doc "A block whose kind is one of the scan set's, e.g. `AND`, `TON`, `SEL`."
  def block(id, kind, pins), do: %Block{id: id, kind: kind, sig: nil, pins: pins}

  @doc "A block that calls a signature from a loaded table."
  def call(id, sig, pins), do: %Block{id: id, kind: "CALL", sig: sig, pins: pins}

  def add_block(%Program{} = p, %Block{} = b), do: %{p | blocks: p.blocks ++ [b]}

  def write(%Program{} = p, name, value), do: %{p | writes: p.writes ++ [{name, value}]}

  def print(%Program{} = p) do
    lines =
      ["program #{p.name}"] ++
        Enum.map(p.ins, &decl("in", &1)) ++
        Enum.map(p.outs, &decl("out", &1)) ++
        Enum.map(p.vars, &decl("var", &1)) ++
        Enum.map(p.blocks, &block_line/1) ++
        Enum.map(p.writes, fn {name, value} -> "#{name} = #{value(value)}" end)

    Enum.join(lines, "\n") <> "\n"
  end

  defp decl(keyword, {name, type}), do: "#{keyword} #{name} : #{type}"

  defp block_line(%Block{kind: "CALL", sig: sig} = b) when is_binary(sig) do
    "#{b.id} = CALL[#{sig}](#{pins(b.pins)})"
  end

  defp block_line(%Block{} = b), do: "#{b.id} = #{b.kind}(#{pins(b.pins)})"

  defp pins(pins), do: Enum.map_join(pins, ", ", fn {name, v} -> "#{name}=#{value(v)}" end)

  def value({:ref, id, pin}), do: "#{id}.#{pin}"
  def value({:var, name}), do: name
  def value({:int, n}), do: Integer.to_string(n)
  def value({:bool, true}), do: "TRUE"
  def value({:bool, false}), do: "FALSE"
  def value({:string, s}), do: ~s("#{check_string(s)}")
  def value({:code, book, digits}), do: "#{book}##{Enum.join(digits, ".")}"
  def value({:time_ms, ms}) when rem(ms, 1000) == 0, do: "T##{div(ms, 1000)}s"
  def value({:time_ms, ms}), do: "T##{ms}ms"

  def value({:real, f}) do
    s = :erlang.float_to_binary(f * 1.0, [:short])
    if String.contains?(s, "."), do: s, else: s <> ".0"
  end

  @forbidden ~c"\"'<>&"

  defp check_string(s) do
    if String.contains?(s, Enum.map(@forbidden, &<<&1>>)) do
      raise ArgumentError,
            "literal carries a character the PLCopen STRING grammar forbids: #{inspect(s)}"
    end

    s
  end

  @doc "Replaces one pin's value on one block, the shape every rank3 mutation takes."
  def set_pin(%Program{} = p, block_id, pin, value) do
    update_block(p, block_id, fn b ->
      unless List.keymember?(b.pins, pin, 0),
        do: raise(ArgumentError, "#{block_id} has no pin #{pin}")

      %{b | pins: List.keyreplace(b.pins, pin, 0, {pin, value})}
    end)
  end

  @doc "Swaps two pins' values, which is visible only where the block is not commutative."
  def swap_pins(%Program{} = p, block_id, a, b) do
    update_block(p, block_id, fn blk ->
      {^a, va} = List.keyfind(blk.pins, a, 0)
      {^b, vb} = List.keyfind(blk.pins, b, 0)
      pins = blk.pins |> List.keyreplace(a, 0, {a, vb}) |> List.keyreplace(b, 0, {b, va})
      %{blk | pins: pins}
    end)
  end

  def set_kind(%Program{} = p, block_id, kind), do: update_block(p, block_id, &%{&1 | kind: kind})

  @doc "Drops one pin, which the lowering refuses by pin name; a rank5 shape."
  def drop_pin(%Program{} = p, block_id, pin) do
    update_block(p, block_id, fn b -> %{b | pins: List.keydelete(b.pins, pin, 0)} end)
  end

  defp update_block(%Program{} = p, block_id, fun) do
    case Enum.find_index(p.blocks, &(&1.id == block_id)) do
      nil -> raise ArgumentError, "no block #{block_id} in #{p.name}"
      i -> %{p | blocks: List.update_at(p.blocks, i, fun)}
    end
  end

  @doc "Every value a block reads, for the coverage and mutation passes."
  def values(%Program{} = p) do
    Enum.flat_map(p.blocks, fn b -> Enum.map(b.pins, fn {_name, v} -> v end) end) ++
      Enum.map(p.writes, fn {_name, v} -> v end)
  end

  @doc "The signatures this program calls, which the census counts against the tables."
  def signatures(%Program{} = p) do
    for %Block{kind: "CALL", sig: sig} <- p.blocks, is_binary(sig), do: sig
  end

  @doc "The block kinds this program uses, `CALL` included."
  def kinds(%Program{} = p), do: Enum.map(p.blocks, & &1.kind)
end
