pub fn count_equal(bytes: &[u8], needle: u8) -> usize {
    bytes
        .iter()
        .fold(0, |count, byte| count + (*byte == needle) as usize)
}

pub fn owning_copy(bytes: &[u8], needle: u8) -> usize {
    let owned = bytes.to_vec();
    owned
        .iter()
        .fold(0, |count, byte| count + (*byte == needle) as usize)
}

pub unsafe fn unsafe_count(bytes: &[u8], needle: u8) -> usize {
    bytes
        .iter()
        .fold(0, |count, byte| count + (*byte == needle) as usize)
}

pub fn pointwise(dst: &mut [f32], src: &[f32]) {
    for i in 0..src.len() {
        dst[i] = src[i] * src[i] + 0.25;
    }
}

pub fn guarded(dst: &mut [f32], src: &[f32]) {
    for i in 0..src.len() {
        let x = src[i];
        dst[i] = if x > 0.0 { x } else { 0.0 };
    }
}

pub fn stencil(dst: &mut [f32], src: &[f32]) {
    for i in 0..src.len() {
        if i == 0 || i + 1 >= src.len() {
            dst[i] = src[i];
        } else {
            dst[i] = src[i - 1] * 0.25 + src[i] * 0.5 + src[i + 1] * 0.25;
        }
    }
}

pub fn prefix_scan(dst: &mut [f32], src: &[f32]) {
    let mut sum = 0.0f32;
    for i in 0..src.len() {
        sum += src[i];
        dst[i] = sum;
    }
}

pub fn recurrence(dst: &mut [f32], src: &[f32]) {
    let mut y = 0.0f32;
    for i in 0..src.len() {
        y = y * 0.875 + src[i] * 0.125;
        dst[i] = y;
    }
}

pub fn indirect(dst: &mut [f32], src: &[f32]) {
    for i in 0..src.len() {
        let j = (i * 17) % src.len();
        dst[i] = src[j] * 0.75 + src[i] * 0.25;
    }
}

#[cfg(test)]
mod tests {
    use super::count_equal;

    #[test]
    fn counts_adversarial_inputs() {
        assert_eq!(count_equal(&[], 7), 0);
        assert_eq!(count_equal(&[7, 0, 7, 255], 7), 2);
        assert_eq!(count_equal(&[3; 257], 3), 257);
    }
}
