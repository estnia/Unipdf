## 行为准则
- **Plan Mode 约束**：在生成任何 Plan 
后，禁止直接调用 Edit/Write 工具。你必须先调用 
`plan_confirmation_flow` 并传入计划摘要。 - 
**循环确认**：若用户提供修改建议，必须更新计划并再次调用 
`plan_confirmation_flow`，直至用户输入“确认”。
