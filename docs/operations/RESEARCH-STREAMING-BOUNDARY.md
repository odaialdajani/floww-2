# Bounded native research streaming

The saved-research helper uses the installed Hermes `AIAgent`, its native
chat-completions streaming accumulator and the installed OpenAI SDK SSE decoder.
The HTTP adapter passes bounded bytes incrementally instead of waiting for a
complete JSON body. The exact NVIDIA MiniMax-M3.1-Flash hosted endpoint documents
`stream=true` and `stream_options.include_usage`:
https://docs.api.nvidia.com/nim/reference/minimaxai-minimax-m3-1-flash-infer

The admitted wire contains only the fixed model, the exact two sanitized messages,
`max_tokens` at most 1024, `stream=true` and `stream_options={"include_usage":true}`.
Unknown parameters and non-stream fallbacks are refused. There is one admitted
POST per role, SDK retries zero, native stream retries zero, one native total
attempt, one iteration, no automatic recovery, no executable tools and no
personal/context/session memory. The 25-second HTTP read, 30-second native budget,
35-second helper alarm and 38-second parent deadline are unchanged. The existing
128 KiB response limit now applies during stream consumption. The original
network-stream extension remains available to the native socket-abort control.

Only numeric byte/chunk/event counts and timings, HTTP status, safe finish reason,
bounded numeric usage and a stable refusal code join durable receipts. Raw SSE,
model prose, headers and credentials are not diagnostics. A 202 response is
refused without polling. Missing `[DONE]`, truncated finish, partial transport
failure, oversized response or attempted extra request prevents success. The
closed bid-fact validator still independently checks the complete retained source
packet. Offline fixture results remain ineligible for real acceptance.

Streaming can expose progress before a whole completion is ready; it does not
prove the hosted model will emit its first byte within 25 seconds or finish a
valid answer within the existing budgets. The previously failed admissions and
shared parked circuit remain unchanged. This source change does not admit a live
request, resume a circuit, install a schedule or activate financial actions.

`ops/tests/test_research_stream.py` exercises the preinstalled OpenAI SDK with an
in-memory HTTP transport. An outer audit guard denies sockets, subprocesses and
production private state/bootstrap reads before SDK import; fixture-only OS header
metadata avoids the SDK's optional platform subprocess. The first decoded delta
must reach the caller before later response bytes are produced. Separate native
conversation fixtures exercise the real Hermes streaming path, copied-fact
validation, fault handling and stop-marker isolation using disposable state.
