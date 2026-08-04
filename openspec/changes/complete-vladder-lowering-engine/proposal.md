## Why

The vLadder v1 capability registry names lowerers but does not resolve those names to callable
implementations. Existing source generators are reachable only through specialized commands, so
the public grammar can describe concerns that the public engine cannot plan or emit. This makes
capability discovery ambiguous and prevents agents from reliably distinguishing a searched rule
from a documented hypothesis.

## What Changes

- Add a registry-driven lowering engine with callable family implementations.
- Require deterministic plan lowering for every declared grammar rule.
- Declare source-emission maturity separately from plan-lowering availability.
- Validate importability, family ownership, and complete rule coverage at registry load time.
- Expose lowering validation, inspection, and plan generation through Python and CLI APIs.
- Route operational source families to their existing specialized vLadder backends.
- Fail closed when a caller requests source emission for an unsupported rule or input shape.

## Impact

The change makes the complete vocabulary executable as optimization planning and legality work.
It does not claim that arbitrary C/C++ source can already be regenerated for every rule. Source
emission remains explicit, shape-gated, and independently testable.
