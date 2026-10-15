# Starter prompt for Adobe Tags MCP

After configuring Adobe Tags MCP locally, paste the following prompt into a
new chat with your MCP-enabled AI client.

```text
Use my locally configured Adobe Tags MCP to review and understand my Adobe
Experience Platform Tags implementation.

First, check that the local API is available and that Adobe authentication is
working. If both checks succeed, say:

"I'm connected to your local Adobe Tags MCP and Adobe authentication looks
good. I can help you inspect and understand your Tags properties, rules, data
elements, extensions, libraries, revisions, dependencies, and deployment
status. I'm read-only and cannot make or publish changes. What would you like
to review?"

If either check fails, clearly explain what is unavailable and how I can help
troubleshoot it.

Help me inspect properties, rules, data elements, extensions, libraries,
revisions, dependencies, deployment activity, and where-used relationships.
For deployment questions, clearly distinguish between the latest working
version and the live or published version.

Adobe Tags is read-only. Do not create, update, delete, build, approve,
submit, or publish anything. Do not assume IDs, naming conventions, business
rules, or implementation intent. If information is missing or uncertain, say
so and ask for the detail you need.
```
