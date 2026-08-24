# Use Case: Hybrid Conversational AI Platform for Travel Customer Support

| Field | Detail |
|-------|--------|
| **System Name** | Airbnb Automation Platform v2 / AI Assistant |
| **Deployment** | Airbnb (global), customer support for guests and hosts |
| **Domain** | Travel / hospitality / sharing economy |
| **Stage** | Production (evolved from rules-based v1 to LLM-hybrid v2, 2024) |

## System Purpose

Airbnb's Automation Platform v2 is a hybrid conversational AI system that combines LLM-based reasoning with traditional rule-based workflows to handle customer support for guests and hosts on the Airbnb platform. The system evolved from a purely rules-based v1 platform that operated on static, predetermined workflows, which were difficult to scale and unable to handle complex or open-ended user queries without extensive manual configuration. The v2 platform introduces LLM capabilities while deliberately retaining traditional workflows for sensitive operations, creating a hybrid architecture that balances AI flexibility with operational safety.

## Architecture and Components

### Hybrid Architecture
The core architectural decision is the hybrid approach: LLM reasoning handles open-ended, complex interactions while traditional rule-based workflows handle sensitive operations (payment modifications, listing changes, safety-critical actions). This ensures critical processes remain secure and reliable while enabling the AI to handle the long tail of diverse customer inquiries. The hybrid design is not a transitional state — it is the deliberate target architecture.

### Chain of Thought (CoT) Workflow
Airbnb implemented Chain of Thought as a structured workflow on the Automation Platform v2. The core idea is using an LLM as a reasoning engine to determine which tools to use and in what order. The CoT workflow has three key components:

- **CoT IO Handler**: Assembles the prompt, prepares contextual data, collects user input, and handles general data processing before sending it to the LLM. This component manages the information pipeline that feeds the reasoning engine.
- **Tool Manager**: Prepares tool payloads with LLM input and output, manages tool execution, and offers operational features like retry logic and rate limiting. This is the bridge between the LLM's decisions and actual system actions.
- **LLM Adapter**: Provides a customisation layer that facilitates integration with different types of LLMs. This abstraction allows the platform to swap or combine different models without restructuring the workflow.

### Tool System
Tools are the mechanism through which the LLM interacts with Airbnb's systems to solve real problems. Examples include checking a reservation's status, checking listing availability, modifying bookings, or looking up policy details. Tools in the v2 platform are built on the same actions and workflows that were the basic building blocks of the v1 rules-based system, reused because their unified interface and managed execution environment make them well-suited as LLM tools.

### Guardrails Framework
The platform includes a dedicated guardrails framework where engineers from different teams create reusable guardrails. During runtime, guardrails execute in parallel and can leverage different downstream technology stacks:
- **Content moderation guardrails**: Call multiple LLMs to detect violations in communication content (e.g., harassment, scams, policy violations)
- **Tool guardrails**: Use rules to prevent bad execution — for example, preventing updates to listings with invalid configurations

Guardrails are reusable across different conversational flows and are managed as shared infrastructure, not per-workflow custom logic.

### Context Management
The system provides the LLM with comprehensive contextual information to support decision-making:
- Historical interactions with the LLM (conversation history within the session)
- The classified intent of the customer support inquiry
- Current trip information (reservation details, dates, location)
- Point-in-time data retrieval for use cases like offline evaluation (ensuring the system can reconstruct the exact state the model saw at decision time)

### Observability
The platform includes LLM-oriented observability providing detailed insights into each LLM interaction, including latency, token usage, tool calls, and reasoning traces. This observability layer is designed specifically for LLM workloads, not repurposed from traditional application monitoring.

### Prompt Development
A Playground feature bridges the gap between development and production by allowing prompt engineers to iterate on prompts in an environment that mirrors the production tech stack. This reduces the risk of prompts that work in development but fail in production due to environmental differences.

## Integration Points

### Reservation and Booking Systems
The AI assistant has tool access to Airbnb's reservation systems — checking status, modifying bookings, looking up details, and processing changes. These are the same integration points that the v1 rules-based system used, now exposed as tools for the LLM.

### Listing Management
The system can interact with listing data — checking availability, viewing listing details, and (with appropriate guardrails) making modifications to host listings.

### Policy and Knowledge Systems
The assistant accesses Airbnb's policies, terms of service, and support knowledge base to ground its responses in accurate, current policy information.

### Multiple LLM Providers
The LLM Adapter abstraction layer supports integration with different LLM providers. The content moderation guardrails explicitly call "various LLMs" (plural), indicating a multi-model approach at least for safety-critical functions.

## Data Handling and Security

### Sensitive Operations Separation
The hybrid architecture explicitly separates sensitive operations (handled by traditional, deterministic workflows) from open-ended reasoning (handled by the LLM). This architectural boundary is the primary security mechanism — the LLM cannot directly execute sensitive actions without passing through the deterministic workflow layer.

### Tool Guardrails
Rule-based tool guardrails prevent the LLM from executing actions with invalid parameters or in prohibited states. These operate as hard constraints that the LLM cannot override, regardless of its reasoning.

### Guest and Host Data
The system processes guest and host data including reservation details, personal trip information, communication history, and potentially payment-related information (though sensitive payment operations are handled by the deterministic workflow layer).

## Operational Context

### User Demographics
Airbnb serves a global user base of guests and hosts with extreme diversity in language, cultural expectations, technical sophistication, and the nature of their support needs. Support interactions range from simple FAQ queries to complex multi-party disputes involving guests, hosts, and Airbnb policies.

### Scale and Diversity of Inquiries
The customer support workload spans an enormous range of intent types — from routine questions about check-in times to complex resolution of disputes, safety incidents, refund negotiations, and policy interpretations. The v1 rules-based system struggled with this long tail; the v2 hybrid architecture was specifically designed to handle it.

### Evolution from v1
The platform is an evolution, not a greenfield build. The v1 system's actions and workflows are reused as tools in v2, meaning the existing business logic, validation rules, and integration points are preserved. This reduces risk compared to building a new system from scratch.

## Key Stakeholders

- Guests (global, diverse demographics and languages)
- Hosts (property owners/managers, varying technical sophistication)
- Airbnb customer support operations
- Airbnb engineering teams (platform, ML, trust & safety)
- Multiple LLM providers (model suppliers)
- Airbnb trust & safety team (content moderation, policy enforcement)
