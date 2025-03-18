import relativeLinksRule from "markdownlint-rule-relative-links"

const config = {
  config: {
    default: true,
    "relative-links": true,
  },
  globs: ["**/*.md"],
  ignores: ["**/node_modules"],
  customRules: [relativeLinksRule],
}

export default config
