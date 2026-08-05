pub fn rust_scalar_count(data: &[u8], needle: u8) -> usize {
    data.iter().filter(|&&value| value == needle).count()
}

pub fn rust_word_count(data: &[u8], needle: u8) -> usize {
    fn bytewise_equal(lhs: u64, rhs: u64) -> u64 {
        let lo = u64::MAX / 0xff;
        let hi = lo << 7;
        let x = lhs ^ rhs;
        !((((x & !hi).wrapping_add(!hi)) | x) >> 7) & lo
    }
    let mut count = 0usize;
    let mut i = 0usize;
    let splat = (u64::MAX / 0xff).wrapping_mul(needle as u64);
    while data.len() - i >= 8 {
        let word = u64::from_ne_bytes(data[i..i + 8].try_into().unwrap());
        count += bytewise_equal(word, splat).count_ones() as usize;
        i += 8;
    }
    count + data[i..].iter().filter(|&&value| value == needle).count()
}

#[target_feature(enable = "avx2")]
pub unsafe fn rust_avx2_count(data: &[u8], needle: u8) -> usize {
    use std::arch::x86_64::{
        __m256i, _mm256_cmpeq_epi8, _mm256_loadu_si256, _mm256_movemask_epi8,
        _mm256_set1_epi8,
    };
    let mut count = 0usize;
    let mut i = 0usize;
    let needles = _mm256_set1_epi8(needle as i8);
    while data.len() - i >= 32 {
        let values = _mm256_loadu_si256(data.as_ptr().add(i) as *const __m256i);
        let matches = _mm256_cmpeq_epi8(values, needles);
        count += (_mm256_movemask_epi8(matches) as u32).count_ones() as usize;
        i += 32;
    }
    count + data[i..].iter().filter(|&&value| value == needle).count()
}

pub fn rust_scalar_utf8(data: &[u8], _needle: u8) -> usize {
    data.iter().filter(|&&value| (value & 0b1100_0000) != 0b1000_0000).count()
}

pub fn rust_word_utf8(data: &[u8], _needle: u8) -> usize {
    fn is_leading_utf8_byte(values: u64) -> u64 {
        ((!values >> 7) | (values >> 6)) & (u64::MAX / 0xff)
    }
    let mut count = 0usize;
    let mut i = 0usize;
    while data.len() - i >= 8 {
        let word = u64::from_ne_bytes(data[i..i + 8].try_into().unwrap());
        count += is_leading_utf8_byte(word).count_ones() as usize;
        i += 8;
    }
    count + data[i..].iter().filter(|&&value| (value & 0b1100_0000) != 0b1000_0000).count()
}
