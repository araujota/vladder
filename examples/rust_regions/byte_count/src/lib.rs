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
