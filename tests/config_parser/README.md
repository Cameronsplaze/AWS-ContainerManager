# Config Parser Tests

The goal of this section is to verify the config loading, schema, and defaults work as expected. It's responsible for making sure:

- Required values are present
- Values are casted correctly (like ints, bools, lists, etc)
- Defaults are applied when values are missing
- Etc...

Basically, given the config you put into the schema, does it produce the expected output for the rest of the code to use. The scope for this directory **ends** at the config output.
