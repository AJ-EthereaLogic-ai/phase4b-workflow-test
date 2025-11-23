"""
Automated workflow testing script.
Runs all 4 workflows against their corresponding GitHub issues.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from adws.workflows import (
    BackendStandardWorkflow,
    BackendTDDWorkflow,
    FrontendStandardWorkflow,
    FrontendTDDWorkflow
)


class WorkflowTestRunner:
    """Automated test runner for all ADWS workflows."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.results: List[Dict] = []

    async def test_workflow(
        self,
        workflow_class,
        workflow_name: str,
        issue_number: int,
        **kwargs
    ) -> Dict:
        """Test a single workflow and return results."""
        print(f"\n{'=' * 80}")
        print(f"Testing: {workflow_name}")
        print(f"Issue #: {issue_number}")
        print(f"{'=' * 80}\n")

        start_time = datetime.now()

        try:
            # Initialize workflow
            workflow = workflow_class(repo_path=self.repo_path, **kwargs)

            # Execute from issue
            result = await workflow.execute_from_issue(issue_number=issue_number)

            duration = (datetime.now() - start_time).total_seconds()

            test_result = {
                "workflow": workflow_name,
                "issue_number": issue_number,
                "success": result.success,
                "duration_seconds": duration,
                "files_created": len(result.artifacts),
                "branch_name": result.metadata.get("branch_name"),
                "pr_url": result.artifacts[0] if result.artifacts else None,
                "error": None
            }

            print(f"\n✅ {workflow_name} PASSED")
            print(f"   Duration: {duration:.2f}s")
            print(f"   Files: {len(result.artifacts)}")

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            test_result = {
                "workflow": workflow_name,
                "issue_number": issue_number,
                "success": False,
                "duration_seconds": duration,
                "error": str(e)
            }

            print(f"\n❌ {workflow_name} FAILED")
            print(f"   Error: {e}")

        self.results.append(test_result)
        return test_result

    async def run_all_tests(self):
        """Run all workflow tests."""
        print("\n" + "=" * 80)
        print("ADWS WORKFLOW AUTONOMOUS COMPLETION TESTS")
        print("=" * 80)

        # Test 1: Backend Standard
        await self.test_workflow(
            BackendStandardWorkflow,
            "BackendStandardWorkflow",
            issue_number=1,
            working_dir="app/server"
        )

        # Test 2: Backend TDD
        await self.test_workflow(
            BackendTDDWorkflow,
            "BackendTDDWorkflow",
            issue_number=2,
            working_dir="app/server",
            test_directories=["tests"]
        )

        # Test 3: Frontend Standard
        await self.test_workflow(
            FrontendStandardWorkflow,
            "FrontendStandardWorkflow",
            issue_number=3,
            working_dir="app/client"
        )

        # Test 4: Frontend TDD
        await self.test_workflow(
            FrontendTDDWorkflow,
            "FrontendTDDWorkflow",
            issue_number=4,
            working_dir="app/client",
            test_directories=["src/__tests__", "src/components/__tests__"]
        )

        # Generate report
        self.generate_report()

    def generate_report(self):
        """Generate test results report."""
        print("\n" + "=" * 80)
        print("TEST RESULTS SUMMARY")
        print("=" * 80 + "\n")

        passed = sum(1 for r in self.results if r["success"])
        failed = len(self.results) - passed

        print(f"Total Tests: {len(self.results)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Success Rate: {passed / len(self.results) * 100:.1f}%\n")

        # Detailed results
        for result in self.results:
            status = "✅ PASS" if result["success"] else "❌ FAIL"
            print(f"{status} | {result['workflow']}")
            print(f"       Issue #{result['issue_number']}")
            print(f"       Duration: {result.get('duration_seconds', 0):.2f}s")
            if result.get("error"):
                print(f"       Error: {result['error']}")
            print()

        # Save report to JSON
        report_path = Path("workflow_test_results.json")
        with open(report_path, "w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "results": self.results
            }, f, indent=2)

        print(f"📄 Full report saved to: {report_path}")


async def main():
    """Main entry point."""
    repo_path = Path.cwd()
    runner = WorkflowTestRunner(repo_path)
    await runner.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
