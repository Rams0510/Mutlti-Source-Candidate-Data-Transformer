import argparse
import json
import sys
import os
from main import run_pipeline

def main():
    parser = argparse.ArgumentParser(description="Candidate Data Transformer CLI")
    parser.add_argument("--csv", help="Path to recruiter CSV spreadsheet")
    parser.add_argument("--resume", help="Path to resume document (PDF or TXT)")
    parser.add_argument("--github", help="GitHub username to query")
    parser.add_argument("--config", help="Path to runtime projection output configuration JSON")
    parser.add_argument("--output", help="Path to output JSON destination file")
    parser.add_argument("--pretty", action="store_true", help="Format the output JSON nicely")
    parser.add_argument("--validate-only", action="store_true", help="Print schema validation warnings and exit")
    
    args = parser.parse_args()
    
    # Require at least one source
    if not (args.csv or args.resume or args.github):
        parser.print_usage()
        sys.exit(1)
        
    inputs = {}
    sources_provided = []
    
    if args.csv:
        inputs["csv_path"] = args.csv
        sources_provided.append("recruiter_csv")
    if args.resume:
        inputs["resume_path"] = args.resume
        sources_provided.append("resume")
    if args.github:
        inputs["github_username"] = args.github
        sources_provided.append("github")
        
    config = None
    if args.config:
        if not os.path.exists(args.config):
            print(f"\033[91mError: Output config file not found at {args.config}\033[0m", file=sys.stderr)
            sys.exit(1)
        try:
            with open(args.config, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            print(f"\033[91mError: Invalid JSON in output config: {e}\033[0m", file=sys.stderr)
            sys.exit(1)
            
    # Run the pipeline
    result = run_pipeline(inputs, config)
    
    # Check for errors in the output structure
    if isinstance(result, dict) and "error" in result:
        print(f"\033[91mPipeline Error: {result['error']}\033[0m", file=sys.stderr)
        if "partial" in result and result["partial"]:
            print("Partial result build before crash:", file=sys.stderr)
            print(json.dumps(result["partial"], indent=2), file=sys.stderr)
        sys.exit(1)
        
    # Ensure result is iterable for metric calculations
    profiles = result if isinstance(result, list) else [result]
        
    # Handle validate-only mode
    if args.validate_only:
        all_warnings = []
        for p in profiles:
            all_warnings.extend(p.get("_warnings", []))
            
        if all_warnings:
            print("\033[93mValidation Warnings Found:\033[0m")
            for w in all_warnings:
                print(f"  - {w}")
        else:
            print("\033[92m[OK] Validation successful. Zero warnings.\033[0m")
        return
        
    # Serialize outputs
    indent = 2 if args.pretty else None
    output_str = json.dumps(result, indent=indent)
    
    if args.output:
        # Create output parent directory if it does not exist
        out_dir = os.path.dirname(args.output)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output_str)
        except Exception as e:
            print(f"\033[91mError writing output file: {e}\033[0m", file=sys.stderr)
            sys.exit(1)
    else:
        print(output_str)
        
    # Get pipeline metrics across all processed profiles
    avg_confidence = sum(p.get("overall_confidence", 0.0) for p in profiles) / len(profiles) if profiles else 0.0
        
    # Print complete pipeline status summary in green
    print(f"\033[92m[OK] Pipeline complete | profiles generated: {len(profiles)} | avg confidence: {avg_confidence:.2f} | sources: {sources_provided}\033[0m")

if __name__ == "__main__":
    main()