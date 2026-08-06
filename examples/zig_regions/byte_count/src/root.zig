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

pub fn pointwise(dst: []f32, src: []const f32) void {
    for (0..src.len) |i| dst[i] = src[i] * src[i] + 0.25;
}

pub fn guarded(dst: []f32, src: []const f32) void {
    for (0..src.len) |i| {
        const x = src[i];
        dst[i] = if (x > 0.0) x else 0.0;
    }
}

pub fn stencil(dst: []f32, src: []const f32) void {
    for (0..src.len) |i| {
        if (i == 0 or i + 1 >= src.len) {
            dst[i] = src[i];
        } else {
            dst[i] = src[i - 1] * 0.25 + src[i] * 0.5 + src[i + 1] * 0.25;
        }
    }
}

pub fn prefixScan(dst: []f32, src: []const f32) void {
    var sum: f32 = 0.0;
    for (0..src.len) |i| {
        sum += src[i];
        dst[i] = sum;
    }
}

pub fn recurrence(dst: []f32, src: []const f32) void {
    var y: f32 = 0.0;
    for (0..src.len) |i| {
        y = y * 0.875 + src[i] * 0.125;
        dst[i] = y;
    }
}

pub fn indirect(dst: []f32, src: []const f32) void {
    for (0..src.len) |i| {
        const j = (i * 17) % src.len;
        dst[i] = src[j] * 0.75 + src[i] * 0.25;
    }
}
