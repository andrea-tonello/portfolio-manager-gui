def secant(f, x0, x1, tol=1e-7, max_iter=100):
    """
    Finds a root of the function f using the Secant method.

    Args:
        f (callable): The function to find the root of (f(x)).
        x0 (float): The first initial guess.
        x1 (float): The second initial guess.
        tol (float): The tolerance for convergence. Stops when abs(f(x_n)) < tol.
        max_iter (int): The maximum number of iterations.

    Returns:
        float or None: The estimated root, or None if the method fails to converge.
    """
    
    # Initialize our two points
    x_n_minus_1 = x0
    x_n = x1
    
    for i in range(max_iter):
        # 1. Calculate the function values at the two points
        fx_n = f(x_n)
        fx_n_minus_1 = f(x_n_minus_1)

        # 2. Check for convergence
        if abs(fx_n) < tol:
            print(f"Converged to root {x_n} after {i} iterations.")
            return x_n
        
        # 3. Calculate the denominator of the secant formula
        denominator = fx_n - fx_n_minus_1
        
        # 4. Check for division by zero (or near-zero)
        # This happens if the function values are the same (flat slope)
        if abs(denominator) < 1e-10:
            print("Error: Denominator is zero. Secant method fails.")
            return None

        # 5. Calculate the next guess using the secant formula
        x_n_plus_1 = x_n - fx_n * (x_n - x_n_minus_1) / denominator
        
        # 6. Update the points for the next iteration
        # The current point becomes the previous point
        x_n_minus_1 = x_n
        # The new point becomes the current point
        x_n = x_n_plus_1

    # If the loop finishes without converging
    print(f"Error: Did not converge after {max_iter} iterations.")
    return None