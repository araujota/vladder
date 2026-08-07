## ADDED Requirements

### Requirement: Structural de-identification
The exporter SHALL remove source identifiers, symbols, paths, user-defined type names, raw
literals, and artifacts; remap graph IDs locally; and expose only declared public vocabulary and
bounded numeric descriptors.

#### Scenario: Proprietary symbol in graph
- **WHEN** a node or obligation contains a project-specific symbol or source path
- **THEN** the transmitted graph contains neither the value nor its repeatable plain hash

### Requirement: Consent-epoch identities
Linkable identifiers SHALL use HMAC-SHA256 under an owner-only installation-local consent-epoch
key that is never transmitted.

#### Scenario: Same root on two installations
- **WHEN** two installations export the same canonical root
- **THEN** their transmitted root IDs differ while candidates within one installation remain groupable

### Requirement: Honest residual-risk classification
The record and user notice SHALL classify graph topology as pseudonymized structural data with
residual algorithm-fingerprinting risk and SHALL NOT claim full anonymity.

#### Scenario: Existing training opt-in
- **WHEN** a saved training decision predates topology disclosure
- **THEN** vLadder reports training consent as unknown and performs no v2 submission until renewed
