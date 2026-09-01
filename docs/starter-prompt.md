# Starter prompt for Adobe Tags MCP

After configuring Adobe Tags MCP locally, paste the following prompt into a
new chat with your MCP-enabled AI client.

```text
Use my locally configured Adobe Tags MCP to help me review and understand my
Adobe Experience Platform Tags implementation.

Start by checking that the local MCP/API and Adobe authentication are available.
Then list the available properties and ask me to choose a property before
reviewing implementation details.

Help me inspect rules, data elements, extensions, libraries, revisions,
dependencies, deployment activity, and where-used relationships as needed.
For deployment questions, clearly distinguish between the latest working
version and the live/published version.

Treat Adobe Tags as read-only. Do not suggest or attempt create, update,
delete, build, approve, submit, or publish actions.

Do not assume property IDs, resource IDs, naming conventions, business rules,
or implementation intent. If information is missing or uncertain, say so
clearly and ask me for the required detail. Do not invent an answer.

Use external sources only when they are necessary. When researching Adobe
behavior or implementation guidance, use Adobe official documentation first,
then Adobe Experience League Community references. Clearly state when an
answer is based on documentation rather than my local Tags configuration.
```
