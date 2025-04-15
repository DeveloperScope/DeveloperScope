import lizard
import radon.metrics

# Cyclomatic Complexity
results = lizard.analyze_file("example.py")

for func in results.function_list:
    print(
        f"Function: {func.name}," +
        f"Cyclomatic Complexity: {func.cyclomatic_complexity}")

# Halstead metrics
with open('example.py', 'r') as file:
    content = file.read()

halstead = radon.metrics.h_visit(content)
print(halstead)
