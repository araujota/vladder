#include <span>
#include <string>
#include <vector>

bool copy_names(
    std::span<const std::string> names,
    std::vector<std::string>& output) noexcept {
    if (output.capacity() - output.size() < names.size()) {
        return false;
    }
    for (const std::string& name : names) {
        output.push_back(name);
    }
    return true;
}
