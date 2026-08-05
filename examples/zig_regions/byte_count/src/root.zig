pub fn countEqual(bytes: []const u8, needle: u8) usize {
    var count: usize = 0;
    for (bytes) |value| {
        count += @intFromBool(value == needle);
    }
    return count;
}

pub fn owningCopy(allocator: anytype, bytes: []const u8) ![]u8 {
    return allocator.dupe(u8, bytes);
}

pub fn volatileCount(bytes: []const volatile u8, needle: u8) usize {
    var count: usize = 0;
    for (bytes) |value| count += @intFromBool(value == needle);
    return count;
}
