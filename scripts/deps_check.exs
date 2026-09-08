alias Explorer.DataFrame, as: DF
alias Explorer.Series
png = Series.from_list([<<137, 80, 78, 71, 0, 255>>], dtype: :binary)
df = DF.new(sub_id: Series.from_list([24], dtype: {:s, 16}), trial: Series.from_list([1], dtype: {:s, 8}), png: png)
path = Path.join(System.tmp_dir!(), "fbd_roundtrip.parquet")
:ok = DF.to_parquet(df, path, compression: {:zstd, 3})
back = DF.from_parquet!(path)
IO.inspect(DF.dtypes(back), label: "dtypes")
[row] = DF.to_rows(back)
true = row["png"] == <<137, 80, 78, 71, 0, 255>>
IO.puts("roundtrip ok, #{File.stat!(path).size} bytes on disk")
{:ok, tok} = Tokenizers.Tokenizer.from_pretrained("bert-base-uncased")
IO.inspect(Tokenizers.Tokenizer.get_vocab_size(tok), label: "vocab")
