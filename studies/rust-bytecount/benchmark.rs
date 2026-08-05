extern crate bytecount;

use std::hint::black_box;
use std::time::Instant;

fn next_u64(state: &mut u64) -> u64 {
    *state ^= *state << 13;
    *state ^= *state >> 7;
    *state ^= *state << 17;
    *state
}

fn invoke(mode: &str, data: &[u8], needle: u8) -> usize {
    match mode {
        "production" => bytecount::count(data, needle),
        "naive" => bytecount::naive_count(data, needle),
        _ => panic!("unknown benchmark mode: {}", mode),
    }
}

fn main() {
    let mode = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "verify".to_string());
    let n = std::env::var("VLADDER_N")
        .ok()
        .and_then(|value| value.parse().ok())
        .unwrap_or(1 << 20);
    let inner = std::env::var("VLADDER_INNER")
        .ok()
        .and_then(|value| value.parse().ok())
        .unwrap_or(256usize);
    let needle = 0x7fu8;
    let mut state = 0x4d595df4d0f33173u64;
    let mut data = Vec::with_capacity(n);
    for _ in 0..n {
        data.push(next_u64(&mut state) as u8);
    }
    for length in 0..=257usize {
        let sample = &data[..length.min(data.len())];
        assert_eq!(bytecount::count(sample, needle), bytecount::naive_count(sample, needle));
    }
    if mode == "verify" {
        println!(r#"{{"status":"PASS","observable":"verification-complete","metric_ns":0}}"#);
        return;
    }
    let expected = bytecount::naive_count(&data, needle);
    assert_eq!(invoke(&mode, &data, needle), expected);
    let start = Instant::now();
    let mut checksum = 0usize;
    for _ in 0..inner {
        checksum = checksum.wrapping_add(black_box(invoke(
            black_box(&mode),
            black_box(&data),
            black_box(needle),
        )));
    }
    let metric = start.elapsed().as_nanos() as f64 / inner as f64;
    println!(
        r#"{{"metric_ns":{:.3},"observable":"{}","checksum":{}}}"#,
        metric, expected, checksum
    );
}
