mod cli;
use clap::Parser;
fn main() {
    let cli = cli::Cli::parse();
    let code = match cli::run(cli) {
        Ok(code) => code,
        Err(error) => {
            eprintln!("nobotrs: {error}");
            2
        }
    };
    std::process::exit(code);
}
