// https://github.com/theoludwig/markdownlint-rule-relative-links

import relativeLinksRule from "markdownlint-rule-relative-links"

const config = {
  config: {
    default: true,
    "relative-links": {
      // Theoretically helps linter resolve paths that start
      // with '/', but can't get it working locally. Use './':
      root_path: ".",
    },
  },
  globs: ["**/*.md"],
  ignores: [
    "**/node_modules",
    ".github/pull_request_template.md",
    ".tox/",
    ".venv/",
  ],
  customRules: [relativeLinksRule],
}

export default config
