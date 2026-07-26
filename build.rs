fn main() {
    println!("cargo:rerun-if-changed=dictionary/entries.json");
}
