#include "ggml.h"
#include "ggml-cpu.h"

#include <cmath>
#include <cstdint>
#include <cinttypes>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <x86intrin.h>

static std::uint64_t ticks() {
    unsigned aux;
    _mm_lfence();
    const std::uint64_t value = __rdtscp(&aux);
    _mm_lfence();
    return value;
}

int main(int argc, char ** argv) {
    const int dimension = argc > 1 ? std::atoi(argv[1]) : 4096;
    const int samples = argc > 2 ? std::atoi(argv[2]) : 12000;
    ggml_init_params params = { 64u * 1024u * 1024u, nullptr, false };
    ggml_context * ctx = ggml_init(params);
    if (!ctx) return 2;
    ggml_tensor * x = ggml_new_tensor_1d(ctx, GGML_TYPE_F32, dimension);
    ggml_tensor * residual = ggml_new_tensor_1d(ctx, GGML_TYPE_F32, dimension);
    ggml_tensor * weight = ggml_new_tensor_1d(ctx, GGML_TYPE_F32, dimension);
    float * xd = static_cast<float *>(x->data);
    float * rd = static_cast<float *>(residual->data);
    float * wd = static_cast<float *>(weight->data);
    for (int i = 0; i < dimension; ++i) {
        xd[i] = std::sin(float(i) * 0.01f);
        rd[i] = std::cos(float(i) * 0.017f) * 0.25f;
        wd[i] = 0.5f + float(i % 31) * 0.01f;
    }
    ggml_tensor * add = ggml_add(ctx, x, residual);
    ggml_tensor * rms = ggml_rms_norm(ctx, add, 1.0e-5f);
    ggml_tensor * out = ggml_mul(ctx, rms, weight);
    ggml_cgraph * graph = ggml_new_graph(ctx);
    ggml_build_forward_expand(graph, out);
    for (int warm = 0; warm < 100; ++warm) if (ggml_graph_compute_with_ctx(ctx, graph, 1) != GGML_STATUS_SUCCESS) return 3;
    double * cycles = static_cast<double *>(std::calloc(static_cast<std::size_t>(samples), sizeof(double)));
    volatile double guard = 0.0;
    for (int sample = 0; sample < samples; ++sample) {
        const std::uint64_t begin = ticks();
        if (ggml_graph_compute_with_ctx(ctx, graph, 1) != GGML_STATUS_SUCCESS) return 4;
        const std::uint64_t end = ticks();
        cycles[sample] = double(end - begin);
        guard += static_cast<float *>(out->data)[sample % dimension];
    }
    std::uint64_t output_hash = UINT64_C(1469598103934665603);
    const auto * output_bytes = static_cast<const unsigned char *>(out->data);
    for (std::size_t i = 0; i < static_cast<std::size_t>(dimension) * sizeof(float); ++i) {
        output_hash ^= output_bytes[i];
        output_hash *= UINT64_C(1099511628211);
    }
    std::printf("{\"dimension\":%d,\"samples\":%d,\"checksum\":%.17g,\"output_hash\":\"%016" PRIx64 "\",\"cycles\":[", dimension, samples, guard, output_hash);
    for (int sample = 0; sample < samples; ++sample) std::printf("%s%.0f", sample ? "," : "", cycles[sample]);
    std::printf("]}\n");
    std::free(cycles);
    ggml_free(ctx);
    return 0;
}
