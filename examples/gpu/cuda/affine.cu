#include <cstddef>

extern "C" __global__ void vladder_transform(
    float *dst,
    const float *src,
    std::size_t n) {
    const std::size_t i =
        static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    if (i < n) {
        dst[i] = src[i] * 2.0f + 1.0f;
    }
}
