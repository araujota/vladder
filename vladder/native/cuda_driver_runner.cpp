#include <cuda.h>

#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

void check(CUresult result, const char *operation) {
    if (result == CUDA_SUCCESS) {
        return;
    }
    const char *name = nullptr;
    const char *message = nullptr;
    cuGetErrorName(result, &name);
    cuGetErrorString(result, &message);
    throw std::runtime_error(std::string(operation) + ": " +
                             (name ? name : "CUDA_ERROR") + " (" +
                             (message ? message : "unknown") + ")");
}

std::string argument(int argc, char **argv, const std::string &name,
                     const std::string &fallback = "") {
    for (int index = 1; index + 1 < argc; ++index) {
        if (argv[index] == name) {
            return argv[index + 1];
        }
    }
    return fallback;
}

bool flag(int argc, char **argv, const std::string &name) {
    for (int index = 1; index < argc; ++index) {
        if (argv[index] == name) {
            return true;
        }
    }
    return false;
}

std::string uuid_string(const CUuuid &uuid) {
    static constexpr int groups[] = {4, 2, 2, 2, 6};
    std::ostringstream stream;
    stream << "GPU-" << std::hex << std::setfill('0');
    int offset = 0;
    for (int group = 0; group < 5; ++group) {
        if (group != 0) {
            stream << '-';
        }
        for (int byte = 0; byte < groups[group]; ++byte) {
            stream << std::setw(2)
                   << static_cast<unsigned int>(
                          static_cast<unsigned char>(uuid.bytes[offset++]));
        }
    }
    return stream.str();
}

int attribute(CUdevice device, CUdevice_attribute name) {
    int value = 0;
    check(cuDeviceGetAttribute(&value, name, device), "cuDeviceGetAttribute");
    return value;
}

void emit_probe(CUdevice device) {
    char name[256] = {};
    CUuuid uuid{};
    check(cuDeviceGetName(name, sizeof(name), device), "cuDeviceGetName");
    check(cuDeviceGetUuid(&uuid, device), "cuDeviceGetUuid");
    const int warp_size = attribute(device, CU_DEVICE_ATTRIBUTE_WARP_SIZE);
    const int max_threads_sm =
        attribute(device, CU_DEVICE_ATTRIBUTE_MAX_THREADS_PER_MULTIPROCESSOR);
    const int memory_clock_khz =
        attribute(device, CU_DEVICE_ATTRIBUTE_MEMORY_CLOCK_RATE);
    const int bus_width_bits =
        attribute(device, CU_DEVICE_ATTRIBUTE_GLOBAL_MEMORY_BUS_WIDTH);
    const double theoretical_bandwidth =
        2.0 * static_cast<double>(memory_clock_khz) * 1000.0 *
        static_cast<double>(bus_width_bits) / 8.0;

    std::cout << '{'
              << "\"vendor\":\"nvidia\"," 
              << "\"name\":\"" << name << "\"," 
              << "\"architecture\":\"sm_"
              << attribute(device, CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MAJOR)
              << attribute(device, CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MINOR)
              << "\"," 
              << "\"device_uuid\":\"" << uuid_string(uuid) << "\"," 
              << "\"warp_size\":" << warp_size << ','
              << "\"multiprocessors\":"
              << attribute(device, CU_DEVICE_ATTRIBUTE_MULTIPROCESSOR_COUNT) << ','
              << "\"max_threads_per_block\":"
              << attribute(device, CU_DEVICE_ATTRIBUTE_MAX_THREADS_PER_BLOCK) << ','
              << "\"max_grid_dim_x\":"
              << attribute(device, CU_DEVICE_ATTRIBUTE_MAX_GRID_DIM_X) << ','
              << "\"max_threads_per_sm\":" << max_threads_sm << ','
              << "\"max_blocks_per_sm\":"
              << attribute(device, CU_DEVICE_ATTRIBUTE_MAX_BLOCKS_PER_MULTIPROCESSOR)
              << ','
              << "\"max_warps_per_sm\":" << max_threads_sm / warp_size << ','
              << "\"registers_per_sm\":"
              << attribute(device, CU_DEVICE_ATTRIBUTE_MAX_REGISTERS_PER_MULTIPROCESSOR)
              << ','
              << "\"shared_memory_per_sm\":"
              << attribute(device, CU_DEVICE_ATTRIBUTE_MAX_SHARED_MEMORY_PER_MULTIPROCESSOR)
              << ','
              << "\"shared_memory_per_block\":"
              << attribute(device, CU_DEVICE_ATTRIBUTE_MAX_SHARED_MEMORY_PER_BLOCK_OPTIN)
              << ','
              << "\"clock_hz\":"
              << static_cast<std::int64_t>(
                     attribute(device, CU_DEVICE_ATTRIBUTE_CLOCK_RATE)) *
                     1000LL
              << ','
              << "\"memory_clock_hz\":"
              << static_cast<std::int64_t>(memory_clock_khz) * 1000LL << ','
              << "\"memory_bus_width_bits\":" << bus_width_bits << ','
              << "\"pci_domain_id\":"
              << attribute(device, CU_DEVICE_ATTRIBUTE_PCI_DOMAIN_ID) << ','
              << "\"pci_bus_id\":"
              << attribute(device, CU_DEVICE_ATTRIBUTE_PCI_BUS_ID) << ','
              << "\"pci_device_id\":"
              << attribute(device, CU_DEVICE_ATTRIBUTE_PCI_DEVICE_ID) << ','
              << "\"gpu_direct_rdma_supported\":"
              << attribute(device, CU_DEVICE_ATTRIBUTE_GPU_DIRECT_RDMA_SUPPORTED) << ','
              << "\"gpu_direct_rdma_flush_writes_options\":"
              << attribute(device, CU_DEVICE_ATTRIBUTE_GPU_DIRECT_RDMA_FLUSH_WRITES_OPTIONS) << ','
              << "\"gpu_direct_rdma_writes_ordering\":"
              << attribute(device, CU_DEVICE_ATTRIBUTE_GPU_DIRECT_RDMA_WRITES_ORDERING) << ','
              << "\"theoretical_memory_bandwidth_bytes_per_second\":"
              << std::fixed << std::setprecision(0) << theoretical_bandwidth
              << "}\n";
}

std::uint64_t fnv1a(const std::vector<float> &values) {
    const auto *bytes = reinterpret_cast<const unsigned char *>(values.data());
    const std::size_t size = values.size() * sizeof(float);
    std::uint64_t hash = 1469598103934665603ULL;
    for (std::size_t index = 0; index < size; ++index) {
        hash ^= bytes[index];
        hash *= 1099511628211ULL;
    }
    return hash;
}

void inspect_kernel(CUdevice device, int argc, char **argv) {
    const std::string module_path = argument(argc, argv, "--module");
    const std::string entry = argument(argc, argv, "--entry", "vladder_transform");
    if (module_path.empty()) {
        throw std::runtime_error("--inspect-module requires --module");
    }
    CUcontext context{};
    CUmodule module{};
    CUfunction function{};
    check(cuCtxCreate(&context, nullptr, 0, device), "cuCtxCreate");
    try {
        check(cuModuleLoad(&module, module_path.c_str()), "cuModuleLoad");
        check(cuModuleGetFunction(&function, module, entry.c_str()),
              "cuModuleGetFunction");
        auto function_attribute = [&](CUfunction_attribute attribute_name) {
            int value = 0;
            check(cuFuncGetAttribute(&value, attribute_name, function),
                  "cuFuncGetAttribute");
            return value;
        };
        CUuuid uuid{};
        check(cuDeviceGetUuid(&uuid, device), "cuDeviceGetUuid");
        std::cout << '{'
                  << "\"entry_point\":\"" << entry << "\"," 
                  << "\"device_identity\":\"" << uuid_string(uuid) << "\"," 
                  << "\"registers_per_thread\":"
                  << function_attribute(CU_FUNC_ATTRIBUTE_NUM_REGS) << ','
                  << "\"static_shared_bytes\":"
                  << function_attribute(CU_FUNC_ATTRIBUTE_SHARED_SIZE_BYTES) << ','
                  << "\"local_bytes_per_thread\":"
                  << function_attribute(CU_FUNC_ATTRIBUTE_LOCAL_SIZE_BYTES) << ','
                  << "\"max_threads_per_block\":"
                  << function_attribute(CU_FUNC_ATTRIBUTE_MAX_THREADS_PER_BLOCK) << ','
                  << "\"ptx_version\":"
                  << function_attribute(CU_FUNC_ATTRIBUTE_PTX_VERSION) << ','
                  << "\"binary_version\":"
                  << function_attribute(CU_FUNC_ATTRIBUTE_BINARY_VERSION)
                  << "}\n";
    } catch (...) {
        if (module) cuModuleUnload(module);
        cuCtxDestroy(context);
        throw;
    }
    if (module) check(cuModuleUnload(module), "cuModuleUnload");
    check(cuCtxDestroy(context), "cuCtxDestroy");
}

void run_kernel(CUdevice device, int argc, char **argv) {
    const std::string module_path = argument(argc, argv, "--module");
    const std::string entry = argument(argc, argv, "--entry", "vladder_transform");
    const std::size_t extent =
        static_cast<std::size_t>(std::stoull(argument(argc, argv, "--n", "1048576")));
    const unsigned int threads =
        static_cast<unsigned int>(std::stoul(argument(argc, argv, "--threads", "256")));
    const unsigned int elements_per_thread = static_cast<unsigned int>(
        std::stoul(argument(argc, argv, "--elements-per-thread", "1")));
    const int warmup = std::stoi(argument(argc, argv, "--warmup", "10"));
    const int iterations = std::stoi(argument(argc, argv, "--iterations", "100"));
    if (module_path.empty() || extent == 0 || threads == 0 ||
        elements_per_thread == 0 || iterations <= 0) {
        throw std::runtime_error("invalid or missing kernel-run arguments");
    }

    CUcontext context{};
    CUmodule module{};
    CUfunction function{};
    CUdeviceptr device_source{};
    CUdeviceptr device_destination{};
    CUevent start{};
    CUevent stop{};
    check(cuCtxCreate(&context, nullptr, 0, device), "cuCtxCreate");
    try {
        check(cuModuleLoad(&module, module_path.c_str()), "cuModuleLoad");
        check(cuModuleGetFunction(&function, module, entry.c_str()),
              "cuModuleGetFunction");
        const std::size_t bytes = extent * sizeof(float);
        check(cuMemAlloc(&device_source, bytes), "cuMemAlloc(source)");
        check(cuMemAlloc(&device_destination, bytes), "cuMemAlloc(destination)");
        std::vector<float> source(extent);
        std::vector<float> destination(extent, 0.0F);
        for (std::size_t index = 0; index < extent; ++index) {
            const int centered = static_cast<int>(index % 8191U) - 4095;
            source[index] = static_cast<float>(centered) / 257.0F;
        }
        check(cuMemcpyHtoD(device_source, source.data(), bytes), "cuMemcpyHtoD");
        check(cuMemsetD8(device_destination, 0xA5, bytes), "cuMemsetD8");

        const std::size_t tile = static_cast<std::size_t>(threads) * elements_per_thread;
        const std::size_t blocks_size = extent / tile + (extent % tile != 0 ? 1 : 0);
        const auto max_grid_x = static_cast<std::size_t>(
            attribute(device, CU_DEVICE_ATTRIBUTE_MAX_GRID_DIM_X));
        if (blocks_size > max_grid_x) {
            throw std::runtime_error("logical extent exceeds the device grid-x limit for this schedule");
        }
        const unsigned int blocks = static_cast<unsigned int>(blocks_size);
        std::uint64_t extent_argument = static_cast<std::uint64_t>(extent);
        void *arguments[] = {&device_destination, &device_source, &extent_argument};
        auto launch = [&]() {
            check(cuLaunchKernel(function, blocks, 1, 1, threads, 1, 1, 0, nullptr,
                                 arguments, nullptr),
                  "cuLaunchKernel");
        };
        for (int index = 0; index < warmup; ++index) {
            launch();
        }
        check(cuCtxSynchronize(), "cuCtxSynchronize(warmup)");
        check(cuEventCreate(&start, CU_EVENT_DEFAULT), "cuEventCreate(start)");
        check(cuEventCreate(&stop, CU_EVENT_DEFAULT), "cuEventCreate(stop)");
        check(cuEventRecord(start, nullptr), "cuEventRecord(start)");
        for (int index = 0; index < iterations; ++index) {
            launch();
        }
        check(cuEventRecord(stop, nullptr), "cuEventRecord(stop)");
        check(cuEventSynchronize(stop), "cuEventSynchronize(stop)");
        float elapsed_ms = 0.0F;
        check(cuEventElapsedTime(&elapsed_ms, start, stop), "cuEventElapsedTime");
        check(cuMemcpyDtoH(destination.data(), device_destination, bytes),
              "cuMemcpyDtoH");
        CUuuid uuid{};
        check(cuDeviceGetUuid(&uuid, device), "cuDeviceGetUuid");
        std::ostringstream hash;
        hash << std::hex << std::setfill('0') << std::setw(16) << fnv1a(destination);
        const double nanoseconds =
            static_cast<double>(elapsed_ms) * 1000000.0 / iterations;
        std::cout << '{'
                  << "\"gpu_time_ns\":" << std::fixed << std::setprecision(3)
                  << nanoseconds << ','
                  << "\"output_hash\":\"fnv1a64:" << hash.str() << "\"," 
                  << "\"device_identity\":\"" << uuid_string(uuid) << "\"," 
                  << "\"evidence_class\":\"hardware-device-timestamp\"," 
                  << "\"blocks\":" << blocks << ','
                  << "\"threads\":" << threads << ','
                  << "\"elements_per_thread\":" << elements_per_thread << ','
                  << "\"logical_extent\":" << extent << "}\n";
    } catch (...) {
        if (start) cuEventDestroy(start);
        if (stop) cuEventDestroy(stop);
        if (device_source) cuMemFree(device_source);
        if (device_destination) cuMemFree(device_destination);
        if (module) cuModuleUnload(module);
        cuCtxDestroy(context);
        throw;
    }
    if (start) check(cuEventDestroy(start), "cuEventDestroy(start)");
    if (stop) check(cuEventDestroy(stop), "cuEventDestroy(stop)");
    if (device_source) check(cuMemFree(device_source), "cuMemFree(source)");
    if (device_destination) check(cuMemFree(device_destination), "cuMemFree(destination)");
    if (module) check(cuModuleUnload(module), "cuModuleUnload");
    check(cuCtxDestroy(context), "cuCtxDestroy");
}

}  // namespace

int main(int argc, char **argv) {
    try {
        check(cuInit(0), "cuInit");
        const int device_index = std::stoi(argument(argc, argv, "--device", "0"));
        CUdevice device{};
        check(cuDeviceGet(&device, device_index), "cuDeviceGet");
        if (flag(argc, argv, "--probe")) {
            emit_probe(device);
        } else if (flag(argc, argv, "--inspect-module")) {
            inspect_kernel(device, argc, argv);
        } else {
            run_kernel(device, argc, argv);
        }
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "cuda_driver_runner: " << error.what() << '\n';
        return 1;
    }
}
