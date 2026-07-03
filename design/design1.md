AI Change Impact Analysis & Autonomous API Testing Platform, where the LLM is responsible for reasoning and orchestration, while deterministic tools perform code analysis, API discovery, test execution, and reporting. This keeps the system reliable and reduces unnecessary LLM calls.

High-Level Architecture
                         Developer Raises PR
                                  │
                                  ▼
                    GitHub/GitLab Webhook Trigger
                                  │
                                  ▼
                     Workflow Orchestrator (LangGraph)
                                  │
         ┌──────────────┬──────────────┬──────────────┐
         ▼              ▼              ▼              ▼
   PR Analysis      Code Graph     API Catalog    Knowledge Base
      Agent           Builder         Loader       (OpenAPI, Docs)
         │               │               │
         └───────────────┴───────────────┘
                         │
                         ▼
              Change Impact Analysis Agent
                         │
        Builds Dependency Graph + API Impact Graph
                         │
                         ▼
               Risk & Coverage Analysis Agent
                         │
                         ▼
               Test Generation Agent
                         │
                         ▼
                 Test Data Generation Agent
                         │
                         ▼
                Test Execution Agent
                         │
                         ▼
                Result Analysis Agent
                         │
                         ▼
               Reporting & PR Comment Agent
                         │
        HTML Report + GitHub Comment + Slack
Agent Responsibilities
1. PR Analysis Agent

Input

PR URL
Git diff
Commit history

Output

{
  "changedFiles": [
    "UserController.java",
    "UserService.java"
  ],
  "changedMethods": [
    "getUser",
    "validateAddress"
  ]
}

This agent performs no reasoning beyond collecting structured information.

2. Code Graph Builder

This is the heart of the system.

Instead of looking only at changed files, it builds a graph such as:

UserController
      │
      ▼
UserService
      │
      ▼
UserRepository
      │
      ▼
Database

It also records:

method calls
inheritance
interfaces
annotations
dependency injection
package dependencies

Think of this as a lightweight knowledge graph of your codebase.

3. API Catalog Builder

This creates a searchable map of all APIs.

Example:

GET /users/{id}

↓

UserController.getUser()

↓

UserService.getUser()

↓

UserRepository.find()

Now every endpoint is connected to the underlying implementation.

Enhancement: API Dependency Graph

This is the feature I'd invest in because it makes the system much smarter.

Example:

                    UserService
                   /     |      \
                  /      |       \
                 ▼       ▼        ▼
         GET /users   POST/users   PATCH/users

If UserService changes, the graph immediately tells the agent that all three endpoints are potentially impacted.

Without this graph, you'd only detect changes in the controller layer and could easily miss affected APIs.

4. Change Impact Analysis Agent

Inputs:

Git diff
Code graph
API graph

Reasoning:

PR modified:

validateAddress()

↓

validateAddress() is called by

↓

UserService.createUser()

↓

Used by

↓

POST /users

PUT /users

PATCH /users

Output

{
  "affectedApis": [
    "POST /users",
    "PUT /users",
    "PATCH /users"
  ]
}
5. Risk Analysis Agent

Not every change deserves the same level of testing.

The agent calculates risk.

Example

Change	Risk
Documentation	Low
Logging	Low
Validation	Medium
Business Logic	High
Authentication	Critical
Payment	Critical

Risk determines

number of tests
negative tests
performance checks
security checks
6. Test Generation Agent

Uses

OpenAPI
existing tests
business rules
historical defects
code changes

Produces

Positive Tests

Negative Tests

Boundary Tests

Authentication Tests

Authorization Tests

Schema Validation

Regression Tests

Example

POST /users

✓ Valid user

✓ Duplicate email

✓ Invalid email

✓ Missing name

✓ Missing token

✓ SQL Injection

✓ Long string

✓ Empty payload
7. Test Data Agent

Automatically provisions

users
accounts
orders
products
tokens

using

factory APIs
DB fixtures
synthetic data
mock services
8. Test Execution Agent

Can execute using

REST Assured

Karate

Playwright API

pytest

Postman

It runs only impacted tests.

Instead of

1500 tests

it might run

42 tests

saving significant execution time.

9. Result Analysis Agent

Rather than simply reporting

FAILED

the agent explains

Failure

↓

500

↓

Null Pointer

↓

AddressService

↓

AddressMapper

↓

line 143

↓

Likely caused by missing null validation

This is where the LLM provides value by summarizing logs and stack traces.

10. Reporting Agent

Produces

PR #215

Risk
High

Affected APIs
5

Generated Tests
28

Executed
28

Passed
26

Failed
2

Coverage

Endpoint Coverage
100%

Business Flow Coverage
95%

Branch Coverage
92%

Failure Analysis

OrderService.java

NullPointerException

Recommendation

Handle missing address before mapping

It can automatically

comment on GitHub PR
publish HTML report
upload artifacts
notify Slack or Microsoft Teams
Overall Data Flow
          GitHub PR
              │
              ▼
     PR Analysis Agent
              │
              ▼
      Code Dependency Graph
              │
              ▼
      API Dependency Graph
              │
              ▼
      Change Impact Analysis
              │
              ▼
        Risk Assessment
              │
              ▼
     Test Scenario Generator
              │
              ▼
      Test Data Generator
              │
              ▼
       Test Execution
              │
              ▼
      Failure Analysis
              │
              ▼
     Coverage Calculation
              │
              ▼
      Report Generation
Recommended Technology Stack
Layer	Technology	Why
LLM	GPT-5.5 or a comparable coding-focused model	Strong reasoning for impact analysis, test generation, and failure summaries.
Agent Framework	LangGraph	Supports stateful, multi-step workflows with retries and human-in-the-loop if needed.
Language	Python	Rich AI ecosystem and excellent integration libraries.
Git Integration	GitHub API / GitLab API	Retrieve PRs, diffs, comments, and post status checks.
Code Parsing	Tree-sitter (multi-language), JavaParser (Java), ts-morph (TypeScript)	Build accurate code and call graphs.
Dependency Graph Storage	Neo4j	Naturally models code relationships and enables impact traversal queries.
Embeddings / RAG	pgvector (PostgreSQL) or a vector database	Retrieve API docs, coding standards, and previous defects as context.
API Specification	OpenAPI/Swagger	Source of truth for endpoints, schemas, and parameters.
Test Generation	Jinja2 templates + LLM	Ensures consistent test structure while allowing intelligent scenario creation.
Test Execution	REST Assured (Java), pytest + requests (Python), Karate	Mature, reliable API testing frameworks.
Test Data	Factory APIs, Testcontainers, Faker	Automated, repeatable test data provisioning.
Coverage	JaCoCo (Java), Istanbul/NYC (JavaScript), Coverage.py (Python), plus custom endpoint coverage	Measures code and API coverage.
CI/CD	GitHub Actions, Jenkins, GitLab CI	Trigger the workflow on every PR.
Reporting	Allure Report + GitHub Checks API + Slack/Teams notifications	Rich reports with easy developer feedback.
Observability	OpenTelemetry + Grafana	Monitor agent performance, execution time, and reliability.
Why this architecture?

The key principle is to let each component do what it does best:

Static analysis tools determine code structure and dependencies.
Graph databases efficiently answer "what is affected?" questions.
LLMs reason about business impact, generate meaningful test cases, and explain failures.
Test frameworks execute requests and assertions deterministically.
CI/CD systems orchestrate when the platform runs.

This separation keeps the platform accurate, explainable, and scalable while minimizing unnecessary LLM usage. It also makes it easier to evolve individual components as your codebase or testing needs grow.
