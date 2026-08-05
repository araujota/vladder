#include <vulkan/vulkan.h>

#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

namespace {

std::string json_escape(const char *text) {
    std::string result;
    for (const unsigned char value : std::string(text ? text : "")) {
        switch (value) {
        case '\\': result += "\\\\"; break;
        case '"': result += "\\\""; break;
        case '\n': result += "\\n"; break;
        case '\r': result += "\\r"; break;
        case '\t': result += "\\t"; break;
        default:
            if (value < 0x20) {
                char buffer[7];
                std::snprintf(buffer, sizeof(buffer), "\\u%04x", value);
                result += buffer;
            } else {
                result += static_cast<char>(value);
            }
        }
    }
    return result;
}

std::string uuid_string(const uint8_t *bytes) {
    char output[37];
    std::snprintf(
        output, sizeof(output),
        "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
        bytes[0], bytes[1], bytes[2], bytes[3], bytes[4], bytes[5], bytes[6], bytes[7],
        bytes[8], bytes[9], bytes[10], bytes[11], bytes[12], bytes[13], bytes[14], bytes[15]);
    return output;
}

std::string version_string(uint32_t version) {
    return std::to_string(VK_API_VERSION_MAJOR(version)) + "." +
           std::to_string(VK_API_VERSION_MINOR(version)) + "." +
           std::to_string(VK_API_VERSION_PATCH(version));
}

bool has_extension(const std::vector<VkExtensionProperties> &extensions, const char *name) {
    for (const auto &extension : extensions) {
        if (std::strcmp(extension.extensionName, name) == 0) return true;
    }
    return false;
}

void emit_queue_flags(VkQueueFlags flags) {
    std::printf("[");
    bool first = true;
    const std::array<std::pair<VkQueueFlagBits, const char *>, 5> names{{
        {VK_QUEUE_GRAPHICS_BIT, "graphics"},
        {VK_QUEUE_COMPUTE_BIT, "compute"},
        {VK_QUEUE_TRANSFER_BIT, "transfer"},
        {VK_QUEUE_SPARSE_BINDING_BIT, "sparse_binding"},
        {VK_QUEUE_PROTECTED_BIT, "protected"},
    }};
    for (const auto &[bit, name] : names) {
        if ((flags & bit) == 0) continue;
        std::printf("%s\"%s\"", first ? "" : ",", name);
        first = false;
    }
    std::printf("]");
}

}  // namespace

int main() {
    uint32_t loader_version = VK_API_VERSION_1_0;
    if (vkEnumerateInstanceVersion) vkEnumerateInstanceVersion(&loader_version);

    VkApplicationInfo application{VK_STRUCTURE_TYPE_APPLICATION_INFO};
    application.pApplicationName = "vladder-vulkan-probe";
    application.applicationVersion = 1;
    application.pEngineName = "vladder";
    application.engineVersion = 1;
    application.apiVersion = loader_version < VK_API_VERSION_1_2 ? loader_version : VK_API_VERSION_1_2;
    VkInstanceCreateInfo create_info{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
    create_info.pApplicationInfo = &application;
    VkInstance instance = VK_NULL_HANDLE;
    VkResult result = vkCreateInstance(&create_info, nullptr, &instance);
    if (result != VK_SUCCESS) {
        std::fprintf(stderr, "vkCreateInstance failed: %d\n", static_cast<int>(result));
        return 2;
    }

    uint32_t device_count = 0;
    result = vkEnumeratePhysicalDevices(instance, &device_count, nullptr);
    if (result != VK_SUCCESS || device_count == 0) {
        std::fprintf(stderr, "vkEnumeratePhysicalDevices failed: %d count=%u\n", static_cast<int>(result), device_count);
        vkDestroyInstance(instance, nullptr);
        return 3;
    }
    std::vector<VkPhysicalDevice> devices(device_count);
    vkEnumeratePhysicalDevices(instance, &device_count, devices.data());

    std::printf("{\"schema_version\":\"vladder-vulkan-capability-v1\",\"loader_api_version\":\"%s\",\"devices\":[", version_string(loader_version).c_str());
    for (uint32_t device_index = 0; device_index < device_count; ++device_index) {
        VkPhysicalDevice device = devices[device_index];
        uint32_t extension_count = 0;
        vkEnumerateDeviceExtensionProperties(device, nullptr, &extension_count, nullptr);
        std::vector<VkExtensionProperties> extensions(extension_count);
        if (extension_count) vkEnumerateDeviceExtensionProperties(device, nullptr, &extension_count, extensions.data());

        VkPhysicalDeviceIDProperties identifiers{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_ID_PROPERTIES};
        VkPhysicalDeviceDriverProperties driver{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DRIVER_PROPERTIES};
        VkPhysicalDeviceSubgroupProperties subgroup{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SUBGROUP_PROPERTIES};
        VkPhysicalDevicePCIBusInfoPropertiesEXT pci{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PCI_BUS_INFO_PROPERTIES_EXT};
        VkPhysicalDeviceProperties2 properties{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2};
        properties.pNext = &identifiers;
        identifiers.pNext = &driver;
        driver.pNext = &subgroup;
        if (has_extension(extensions, VK_EXT_PCI_BUS_INFO_EXTENSION_NAME)) subgroup.pNext = &pci;
        vkGetPhysicalDeviceProperties2(device, &properties);

        VkPhysicalDeviceTimelineSemaphoreFeatures timeline{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_TIMELINE_SEMAPHORE_FEATURES};
        VkPhysicalDeviceSynchronization2Features synchronization2{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SYNCHRONIZATION_2_FEATURES};
        VkPhysicalDeviceFeatures2 features{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2};
        features.pNext = &timeline;
        timeline.pNext = &synchronization2;
        vkGetPhysicalDeviceFeatures2(device, &features);

        uint32_t queue_count = 0;
        vkGetPhysicalDeviceQueueFamilyProperties2(device, &queue_count, nullptr);
        std::vector<VkQueueFamilyProperties2> queues(queue_count);
        for (auto &queue : queues) queue.sType = VK_STRUCTURE_TYPE_QUEUE_FAMILY_PROPERTIES_2;
        vkGetPhysicalDeviceQueueFamilyProperties2(device, &queue_count, queues.data());

        VkPhysicalDeviceMemoryProperties memory{};
        vkGetPhysicalDeviceMemoryProperties(device, &memory);

        if (device_index) std::printf(",");
        std::printf(
            "{\"index\":%u,\"name\":\"%s\",\"api_version\":\"%s\",\"driver_version_raw\":%u,"
            "\"vendor_id\":%u,\"device_id\":%u,\"device_type\":%u,\"device_uuid\":\"%s\","
            "\"driver_uuid\":\"%s\",\"driver_name\":\"%s\",\"driver_info\":\"%s\","
            "\"subgroup_size\":%u,\"timeline_semaphore\":%s,\"synchronization2\":%s,",
            device_index, json_escape(properties.properties.deviceName).c_str(),
            version_string(properties.properties.apiVersion).c_str(), properties.properties.driverVersion,
            properties.properties.vendorID, properties.properties.deviceID, properties.properties.deviceType,
            uuid_string(identifiers.deviceUUID).c_str(), uuid_string(identifiers.driverUUID).c_str(),
            json_escape(driver.driverName).c_str(), json_escape(driver.driverInfo).c_str(), subgroup.subgroupSize,
            timeline.timelineSemaphore ? "true" : "false", synchronization2.synchronization2 ? "true" : "false");
        if (has_extension(extensions, VK_EXT_PCI_BUS_INFO_EXTENSION_NAME)) {
            std::printf("\"pci\":{\"domain\":%u,\"bus\":%u,\"device\":%u,\"function\":%u},", pci.pciDomain, pci.pciBus, pci.pciDevice, pci.pciFunction);
        } else {
            std::printf("\"pci\":null,");
        }
        std::printf(
            "\"extensions\":{\"external_memory_fd\":%s,\"external_semaphore_fd\":%s,"
            "\"external_memory_dma_buf\":%s,\"timeline_semaphore\":%s,\"synchronization2\":%s,\"swapchain\":%s},",
            has_extension(extensions, VK_KHR_EXTERNAL_MEMORY_FD_EXTENSION_NAME) ? "true" : "false",
            has_extension(extensions, VK_KHR_EXTERNAL_SEMAPHORE_FD_EXTENSION_NAME) ? "true" : "false",
            has_extension(extensions, VK_EXT_EXTERNAL_MEMORY_DMA_BUF_EXTENSION_NAME) ? "true" : "false",
            has_extension(extensions, VK_KHR_TIMELINE_SEMAPHORE_EXTENSION_NAME) ? "true" : "false",
            has_extension(extensions, VK_KHR_SYNCHRONIZATION_2_EXTENSION_NAME) ? "true" : "false",
            has_extension(extensions, VK_KHR_SWAPCHAIN_EXTENSION_NAME) ? "true" : "false");
        std::printf("\"queue_families\":[");
        for (uint32_t queue_index = 0; queue_index < queue_count; ++queue_index) {
            const auto &queue = queues[queue_index].queueFamilyProperties;
            if (queue_index) std::printf(",");
            std::printf("{\"index\":%u,\"queue_count\":%u,\"timestamp_valid_bits\":%u,\"flags\":", queue_index, queue.queueCount, queue.timestampValidBits);
            emit_queue_flags(queue.queueFlags);
            std::printf(
                ",\"min_image_transfer_granularity\":[%u,%u,%u]}",
                queue.minImageTransferGranularity.width,
                queue.minImageTransferGranularity.height,
                queue.minImageTransferGranularity.depth);
        }
        std::printf("],\"memory_heaps\":[");
        for (uint32_t heap = 0; heap < memory.memoryHeapCount; ++heap) {
            if (heap) std::printf(",");
            std::printf("{\"index\":%u,\"size_bytes\":%llu,\"device_local\":%s}", heap,
                        static_cast<unsigned long long>(memory.memoryHeaps[heap].size),
                        (memory.memoryHeaps[heap].flags & VK_MEMORY_HEAP_DEVICE_LOCAL_BIT) ? "true" : "false");
        }
        std::printf("]}");
    }
    std::printf("],\"status\":\"PASS\"}\n");
    vkDestroyInstance(instance, nullptr);
    return 0;
}
