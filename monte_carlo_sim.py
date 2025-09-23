import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import os
import argparse

def calculate_page_error_ratio_theoretical(page_size_bytes, ber):
    """
    Calculate Page Error Ratio using theoretical probability formula
    
    Args:
        page_size_bytes: Page size in bytes
        ber: Bit Error Rate
    
    Returns:
        Page Error Ratio (probability that at least one bit error occurs in a page)
    """
    # Convert page size to bits
    page_size_bits = page_size_bytes * 8
    
    # Theoretical: 1 - (1 - BER)^(page_size_bits)
    theoretical_page_error_rate = 1.0 - (1.0 - ber) ** page_size_bits
    
    return theoretical_page_error_rate

def calculate_and_save_results(output_file="page_error_theoretical_results.csv"):
    """
    Calculate theoretical Page Error Ratios and save results to CSV file
    """
    # Page sizes (same as ChampSim)
    page_4kb = 4 * 1024  # 4KB in bytes
    page_2mb = 2 * 1024 * 1024  # 2MB in bytes
    
    # BER range from 1e-12 to 1e-4 (truly continuous with many points)
    # Use logspace to create smooth continuous curve
    num_points = 500  # Much more points for truly smooth curve
    ber_values = np.logspace(-12, -4, num_points)  # 1e-12 to 1e-4 with 500 points
    
    print("="*60)
    print("CALCULATING THEORETICAL PAGE ERROR RATIOS")
    print("="*60)
    print(f"Total BER points to calculate: {len(ber_values)}")
    print(f"BER range: {ber_values[0]:.2e} to {ber_values[-1]:.2e}")
    print(f"Output file: {output_file}")
    print()
    
    # Results storage
    results = []
    
    for i, ber in enumerate(ber_values):
        # Show progress every 50 points to avoid too much output
        if i % 50 == 0 or i == len(ber_values) - 1:
            print(f"Progress: {i+1}/{len(ber_values)} (BER: {ber:.2e})")
        
        # Theoretical calculation
        per_4kb_theoretical = calculate_page_error_ratio_theoretical(page_4kb, ber)
        per_2mb_theoretical = calculate_page_error_ratio_theoretical(page_2mb, ber)
        
        # Store results
        results.append({
            'ber': ber,
            'per_4kb_theoretical': per_4kb_theoretical,
            'per_2mb_theoretical': per_2mb_theoretical
        })
    
    # Save to CSV
    df = pd.DataFrame(results)
    df.to_csv(output_file, index=False)
    
    print("="*60)
    print("CALCULATION COMPLETED")
    print("="*60)
    print(f"Results saved to: {output_file}")
    
    return df

def load_results(input_file="page_error_theoretical_results.csv"):
    """
    Load calculated results from CSV file
    """
    if not os.path.exists(input_file):
        print(f"Error: Results file '{input_file}' not found.")
        print("Please run calculation first using: python monte_carlo_sim.py --calculate")
        return None
    
    print(f"Loading results from: {input_file}")
    df = pd.read_csv(input_file)
    print(f"Loaded {len(df)} data points")
    return df

def plot_results(df, output_image="page_error_ratio_theoretical.png"):
    """
    Create plots from calculated results
    """
    if df is None:
        return
    
    # Extract data
    ber_values = df['ber'].values
    per_4kb_theoretical = df['per_4kb_theoretical'].values
    per_2mb_theoretical = df['per_2mb_theoretical'].values
    
    # Create the plot with smaller height
    plt.figure(figsize=(12, 5))
    
    # Plot theoretical results as smooth continuous lines (no markers)
    plt.loglog(ber_values, per_4kb_theoretical, 'b-', linewidth=2, 
               label='4KB Page', alpha=0.9)
    plt.loglog(ber_values, per_2mb_theoretical, 'r-', linewidth=2, 
               label='2MB Page', alpha=0.9)
    
    # Customize the plot
    plt.xlabel('Bit Error Rate (BER)', fontsize=14)
    plt.ylabel('Page Error Ratio', fontsize=14)
    plt.grid(True, alpha=0.3)
    plt.legend(fontsize=12)
    
    # Set axis limits
    plt.xlim(1e-12, 1e-4)
    plt.ylim(1e-8, 1)
    
    plt.tight_layout()
    
    # Save the plot
    plt.savefig(output_image, dpi=300, bbox_inches='tight')
    print(f"Plot saved as: {output_image}")
    plt.show()

def print_summary_statistics(df):
    """
    Print summary statistics from calculated results
    """
    if df is None:
        return
    
    page_4kb = 4 * 1024
    page_2mb = 2 * 1024 * 1024
    ber_values = df['ber'].values
    
    print("\n" + "="*60)
    print("=== THEORETICAL CALCULATION SUMMARY ===")
    print("="*60)
    print(f"Page sizes: 4KB ({page_4kb} bytes = {page_4kb*8:,} bits)")
    print(f"            2MB ({page_2mb} bytes = {page_2mb*8:,} bits)")
    print(f"BER range: {ber_values[0]:.2e} to {ber_values[-1]:.2e}")
    print(f"Number of BER points: {len(ber_values)}")
    
    # Find key threshold points (only show major exponents)
    print("\n=== KEY OBSERVATIONS ===")
    key_exponents = [-12, -10, -8, -6, -4]
    for exp in key_exponents:
        target_ber = 10**exp
        # Find closest BER value in dataset
        idx = np.argmin(np.abs(ber_values - target_ber))
        actual_ber = ber_values[idx]
        per_4kb = df.iloc[idx]['per_4kb_theoretical']
        per_2mb = df.iloc[idx]['per_2mb_theoretical']
        
        if per_4kb > 0:
            ratio = per_2mb / per_4kb
        else:
            ratio = float('inf')
        
        print(f"At BER {actual_ber:.0e}:")
        print(f"  4KB Page Error Ratio: {per_4kb:.6e}")
        print(f"  2MB Page Error Ratio: {per_2mb:.6e}")
        print(f"  Ratio (2MB/4KB): {ratio:.2f}")
        print()
    
    # Find crossover points (when error ratios become significant)
    print("=== SIGNIFICANT ERROR RATE THRESHOLDS ===")
    thresholds = [0.01, 0.1, 0.5, 0.9]
    for threshold in thresholds:
        for page_type in ['4kb', '2mb']:
            col_name = f'per_{page_type}_theoretical'
            idx = np.argmax(df[col_name].values >= threshold)
            if df[col_name].iloc[idx] >= threshold:
                print(f"{threshold*100:g}% error rate reached:")
                print(f"  {'4KB' if page_type == '4kb' else '2MB'} page at BER {ber_values[idx]:.0e}")

def main():
    parser = argparse.ArgumentParser(description='Theoretical calculation for page error rates')
    parser.add_argument('--calculate', action='store_true', 
                       help='Calculate theoretical Page Error Ratios and save results to CSV')
    parser.add_argument('--plot', action='store_true', 
                       help='Load saved results and create plots')
    parser.add_argument('--input', default='page_error_theoretical_results.csv',
                       help='Input CSV file for plotting (default: page_error_theoretical_results.csv)')
    parser.add_argument('--output', default='page_error_theoretical_results.csv',
                       help='Output CSV file for calculation (default: page_error_theoretical_results.csv)')
    parser.add_argument('--image', default='page_error_ratio_theoretical.png',
                       help='Output image file (default: page_error_ratio_theoretical.png)')
    
    args = parser.parse_args()
    
    # If no arguments provided, run calculation and plot
    if not args.calculate and not args.plot:
        if os.path.exists(args.input):
            print("Results found. Loading and plotting...")
            df = load_results(args.input)
            plot_results(df, args.image)
            print_summary_statistics(df)
        else:
            print("No results found. Running calculation first...")
            df = calculate_and_save_results(args.output)
            plot_results(df, args.image)
            print_summary_statistics(df)
    
    elif args.calculate:
        print("Running theoretical calculation...")
        df = calculate_and_save_results(args.output)
        print_summary_statistics(df)
    
    elif args.plot:
        print("Loading saved results and creating plots...")
        df = load_results(args.input)
        plot_results(df, args.image)
        print_summary_statistics(df)

if __name__ == "__main__":
    main()