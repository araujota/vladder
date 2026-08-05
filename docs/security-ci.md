# Security And Quality CI

Core CI always runs Ruff correctness rules, Bandit medium/high-severity and confidence checks, and
the seeded accepted/rejected semantic transformations. These checks require no repository secret.

SonarQube Cloud and Snyk are separate external gates. Configure:

- secret `SONAR_TOKEN` and variables `SONAR_ORGANIZATION`, `SONAR_PROJECT_KEY`;
- secret `SNYK_TOKEN`.

The workflow reports an explicit unconfigured message when credentials are absent. Fork pull
requests do not receive secrets. Before a broad release, maintainers must inspect the GitHub Actions
run and confirm both external scan steps executed; the presence of workflow YAML alone is not a
passing external gate.

Ruff checks syntax, invalid control flow, and undefined names under the published configuration.
Bandit is a heuristic and does not prove command or network safety. Sonar and Snyk findings must be
triaged rather than suppressed solely to obtain a green badge.
