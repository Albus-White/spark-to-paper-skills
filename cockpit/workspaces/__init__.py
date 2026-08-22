"""SparkBoard workspace adapters — thin, stdlib-only readers that turn the
three tools' on-disk artifacts into JSON the reader GUI renders, plus the
restrained reading-AI proxy. No DB, no framework; every function reads a file
the tool already wrote. Imported by serve.py; each module is also runnable as a
`__main__` smoke test against a real sample directory."""
