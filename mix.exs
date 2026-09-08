defmodule TaskweftFbdTeacher.MixProject do
  use Mix.Project

  def project do
    [
      app: :taskweft_fbd_teacher,
      version: "0.1.0",
      elixir: "~> 1.17",
      start_permanent: Mix.env() == :prod,
      deps: deps()
    ]
  end

  def application do
    [extra_applications: [:logger]]
  end

  defp deps do
    [
      {:explorer, "~> 0.12"},
      {:nimble_parsec, "~> 1.4"},
      {:sourceror, "~> 1.12"},
      {:nimble_pool, "~> 1.1"},
      {:jason, "~> 1.4"},
      {:req, "~> 0.5"},
      {:tokenizers, "~> 0.5"}
    ]
  end
end
