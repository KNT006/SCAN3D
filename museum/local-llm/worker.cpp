// SCAN3D one-request RKLLM worker. Process exit releases model and KV memory.
// Compile against Rockchip RKLLM 1.3.0 rkllm.h, not the RKNN vision API.
#include <cstdio>
#include <fstream>
#include <iterator>
#include <string>
#include <sys/resource.h>
#include "rkllm.h"

static std::ofstream output;
static bool failed = false;
static RKLLMPerfStat perf{};
static int callback(RKLLMResult* result, void*, LLMCallState state) {
    if (state == RKLLM_RUN_ERROR) failed = true;
    if (result && state == RKLLM_RUN_NORMAL && result->text) output << result->text;
    if (result && state == RKLLM_RUN_FINISH) perf = result->perf;
    return 0;
}
int main(int argc, char** argv) {
    if (argc != 4) return 2;
    // The deployed BSP lacks the memory cgroup controller. Enforce an address
    // space ceiling in the worker too; the supervisor also watches RSS/free RAM.
    rlimit address_space{3ULL * 1024 * 1024 * 1024, 3ULL * 1024 * 1024 * 1024};
    if (setrlimit(RLIMIT_AS, &address_space) != 0) return 8;
    rlimit core{0, 0};
    setrlimit(RLIMIT_CORE, &core);
    std::ifstream input(argv[2]);
    std::string prompt((std::istreambuf_iterator<char>(input)), {});
    if (prompt.empty() || prompt.size() > 3200) return 3;
    output.open(argv[3]);
    if (!output) return 4;
    LLMHandle handle = nullptr;
    RKLLMParam p = rkllm_createDefaultParam();
    p.model_path = argv[1];
    p.max_context_len = 1024;
    p.max_new_tokens = 160;
    p.top_k = 1;
    p.top_p = 0.9f;
    p.temperature = 0.4f;
    p.repeat_penalty = 1.1f;
    p.skip_special_token = true;
    p.extend_param.embed_flash = 1;
    p.extend_param.enabled_cpus_num = 2;
    p.extend_param.enabled_cpus_mask = CPU4 | CPU5;
    RKLLMCallback cb{};
    cb.result_callback = callback;
    int rc = rkllm_init(&handle, &p, &cb);
    if (rc != 0) return 5;
    // Input already contains the Qwen2 Instruct ChatML template, exactly once.
    rc = rkllm_set_chat_template(handle, "", "", "");
    if (rc != 0) { rkllm_destroy(handle); return 6; }
    RKLLMInput in{};
    in.role = "user";
    in.input_type = RKLLM_INPUT_PROMPT;
    in.prompt_input = prompt.c_str();
    RKLLMInferParam infer{};
    infer.mode = RKLLM_INFER_GENERATE;
    infer.keep_history = 0;
    rc = rkllm_run(handle, &in, &infer, nullptr);
    output.close();
    rkllm_destroy(handle);
    rusage usage{};
    getrusage(RUSAGE_SELF, &usage);
    fprintf(stderr, "SCAN3D_PERF {\"prefill_tokens\":%d,\"prefill_ms\":%.3f,\"generated_tokens\":%d,\"generate_ms\":%.3f,\"peak_rss_kib\":%ld}\n",
        perf.prefill_tokens, perf.prefill_time_ms, perf.generate_tokens, perf.generate_time_ms, usage.ru_maxrss);
    return rc == 0 && !failed ? 0 : 7;
}
