alias Explorer.DataFrame, as: DF
alias Explorer.Series

candidate = fn rank ->
  %{
    "candidate" => "rank#{rank}",
    "rank" => rank,
    "fbd_text" => "rows/t/0/rank#{rank}.fbd",
    "fbd_sha" => String.duplicate("a", 64),
    "traces" => 3,
    "provenance" => "constructed:t:seed:0",
    "scores" => %{
      "candidate" => "rank#{rank}",
      "parses" => true,
      "compiles" => rank != 5,
      "runs" => rank == 1,
      "effect_matches" => rank == 1,
      "steps" => 12,
      "wall_ms" => 340,
      "refusal" => ""
    }
  }
end

rows = [
  %{
    "key" => "t/a/0",
    "intent" => "write x to y",
    "template_id" => "a",
    "seed" => 0,
    "candidates" => Enum.map([1, 3, 5], candidate)
  }
]

df = DF.new(rows)
IO.inspect(DF.dtypes(df), label: "dtypes", limit: :infinity)

path = Path.join(System.tmp_dir!(), "fbd_nested.parquet")
:ok = DF.to_parquet(df, path, compression: {:zstd, 3})
back = DF.from_parquet!(path)
[row] = DF.to_rows(back)

IO.puts(
  "round trip: #{length(row["candidates"])} candidates, first rank #{hd(row["candidates"])["rank"]}"
)

IO.puts("nested score: #{inspect(hd(row["candidates"])["scores"]["compiles"])}")
IO.puts("bytes on disk: #{File.stat!(path).size}")
