# Design Choices for the AWS Architecture

This is a list of design choices I've made on the Architecture

- EC2, can ssh to access EFS. No Data-Sync.
- Not using a circuit breaker anymore. ASG is what costs money, so spin that down. Plus if you got into a state where the ASG was up, but the task was down (like the defaut circuit breaker triggered), you'd have to wait for the watchdog to spin down the ASG before connecting again. This follows the idea of "control the system through the ASG".
