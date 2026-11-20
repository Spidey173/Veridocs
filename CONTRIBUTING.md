# Contributing to Veridocs

Thank you for contributing to Veridocs! To maintain a clear, high-signal codebase and git history, please follow these guidelines.

---

## 1. Commit Style Guide

From milestone 1.0 onward, all commits must follow the **Conventional Commits** specification with a concise subject and a short body explaining **why** the change was made.

### Commit Format

```
<type>(<optional-scope>): <short imperative description>

<short body explaining why the change is being made and any relevant context>
```

### Allowed Types

- `feat:` A new user-facing or platform feature or capability addition.
- `fix:` A bug fix, security vulnerability remedy, or error recovery.
- `test:` Adding, refactoring, or updating unit tests, evaluation benchmarks, or mocks.
- `docs:` Documentation additions, clarifications, or handbook updates.
- `chore:` Tooling, CI/CD configuration, dependencies, or repo maintenance.
- `refactor:` Code restructuring that does not change functional behavior or APIs.
- `perf:` Performance optimizations, query speedups, or memory footprint reductions.
- `build:` Build system, package bundling, or environment changes.
- `ci:` Continuous integration workflow updates.

### Rules & Best Practices

1. **Imperative Mood**: Write the header in the imperative mood ("add feature", "fix issue", not "added" or "fixes").
2. **Concise Header**: Keep the header line under 72 characters, lowercase type, no trailing period.
3. **Mandatory "Why" Body**: Always provide a short body explaining **why** the change was necessary and any non-obvious design decisions.
4. **No Rewriting History**: Never force push or rewrite public branches.

### Examples

#### ✅ Good:
```
feat(auth): gate demo token endpoint behind ENABLE_DEMO_AUTH and restrict privileges

Gate /api/auth/demo-token behind an explicit ENABLE_DEMO_AUTH env flag (defaulting to false)
so routes remain unregistered when disabled. Enforce a startup check refusing to boot when
ENV=production and ENABLE_DEMO_AUTH=true. Restrict demo tokens to role='demo' with a 15-minute
max expiry and prevent elevation to admin or real user roles.
```

```
fix(vector): prevent zero-norm division in cosine normalization

When all token weights in a short fragment evaluate to zero, vector normalization previously
produced NaN vectors that caused pgvector query errors. Fall back to a zero vector when norm is zero.
```

#### ❌ Bad:
- `wip`
- `fixed stuff`
- `feat: update code.`
- `fix: bug` (missing scope, details, and body explaining why)

---

## 2. Enforcing Commit Style

We enforce conventional commits using both a local Git `commit-msg` hook and a `commitlint` configuration.

### Activating the Commit Hook

Run either of the following commands to configure your repository to use the version-controlled hook in `.githooks/`:

```bash
# Via Makefile
make hooks

# Or directly via Git
git config core.hooksPath .githooks
chmod +x .githooks/commit-msg
```

Whenever you run `git commit`, the hook verifies that your commit message follows conventional commit specifications before the commit is created.

### Commitlint Configuration

The repository includes a `.commitlintrc.json` configuration for automated CI enforcement and linting during pull request reviews.

---

## 3. Development & Testing Workflow

Before opening a pull request, ensure all quality gates and tests pass:

```bash
# 1. Run fast unit tests
make test
# Or: pytest backend/tests/unit

# 2. Run the live LLM evaluation harness (evaluates against 40 benchmark cases)
make eval

# 3. Clean temporary files
make clean
```

### Pull Request Checklist

- [ ] Commit headers strictly follow Conventional Commits format (`type(scope): message`).
- [ ] Every commit includes a body explaining **why** the change was made.
- [ ] All fast unit tests pass (`make test`).
- [ ] New functionality includes corresponding unit tests in `tests/unit/`.
- [ ] Any changes affecting factual evaluation are verified with `make eval`.
- [ ] Documentation (`README.md`, `.env.example`, etc.) is updated where applicable.
