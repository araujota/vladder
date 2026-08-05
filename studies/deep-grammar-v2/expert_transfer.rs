extern crate bytecount;

include!(env!("VLADDER_GENERATED_SOURCE"));

use std::hint::black_box;
use std::time::Instant;

fn fill(data: &mut [u8], mut state: u64) {
    for value in data {
        state ^= state >> 12;
        state ^= state << 25;
        state ^= state >> 27;
        state = state.wrapping_mul(2_685_821_657_736_338_717u64);
        *value = state as u8;
    }
}

fn invoke(mode: &str, data: &[u8], needle: u8) -> usize {
    match mode {
        "scalar" => bytecount::naive_count(data, needle),
        "expert" => bytecount::count(data, needle),
        "generated" => deep_candidate(data, needle),
        _ => panic!("unknown mode: {mode}"),
    }
}

fn verify() {
    let mut data = vec![0u8; 521];
    for value in 0u16..=255 {
        data[0] = value as u8;
        for needle in 0u16..=255 {
            let expected = bytecount::naive_count(&data[..1], needle as u8);
            assert_eq!(bytecount::count(&data[..1], needle as u8), expected);
            assert_eq!(deep_candidate(&data[..1], needle as u8), expected);
        }
    }
    for n in 0usize..=520 {
        fill(&mut data[..n], 0x1234_5678_9abc_def0u64 ^ n as u64);
        for &needle in &[0u8, 1, 17, 127, 128, 254, 255] {
            let expected = bytecount::naive_count(&data[..n], needle);
            assert_eq!(bytecount::count(&data[..n], needle), expected);
            assert_eq!(deep_candidate(&data[..n], needle), expected);
        }
    }
}

fn main() {
    verify();
    let args: Vec<String> = std::env::args().collect();
    let mode = args.get(1).map(String::as_str).unwrap_or("verify");
    if mode == "verify" {
        println!(r#"{{"ns_per_call":0,"observable":"verification-complete"}}"#);
        return;
    }
    let n = args.get(2).and_then(|value| value.parse().ok()).unwrap_or(1usize << 20);
    let inner = args.get(3).and_then(|value| value.parse().ok()).unwrap_or(128usize);
    let mut data = vec![0u8; n];
    fill(&mut data, 0x5a17_d33du64);
    let mut guard = 0usize;
    for warm in 0..8 {
        guard = guard.wrapping_add(invoke(mode, black_box(&data), (17 + warm) as u8));
    }
    let begin = Instant::now();
    for index in 0..inner {
        guard = guard.wrapping_add(invoke(
            black_box(mode),
            black_box(&data),
            black_box((17 + (index & 15)) as u8),
        ));
    }
    let elapsed = begin.elapsed().as_nanos() as f64;
    let observable = invoke(mode, &data, 17);
    println!(
        r#"{{"ns_per_call":{:.9},"observable":"{}","guard":"{}"}}"#,
        elapsed / inner as f64,
        observable,
        guard,
    );
}
