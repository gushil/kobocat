pipeline {
    agent any
    environment {
        registry = "837577998611.dkr.ecr.us-west-2.amazonaws.com/kobocat"
        clustername = "eks-sbs-dev"
        region = "us-west-2"
        ns = "sbsdev"
        ecrauth = "aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 837577998611.dkr.ecr.us-west-2.amazonaws.com"
       }
	   
    stages {
        stage('Checkout') {
            steps {
                cleanWs()
                checkout scmGit(branches: [[name: '*/$release_branch'']], extensions: [], userRemoteConfigs: [[credentialsId: 'jenkins-github-token-as-password', url: 'https://github.com/OpenClinica/kobocat.git']])
            }
        }
        stage('Fetch ECR Credentials') {
            steps {
                script {
                    sh "${ecrauth}"
                }
            }
        }
        stage('Configure EKS Cluster') {
            steps {
                sh '/usr/local/bin/eksctl version'
                sh '/usr/local/bin/eksctl utils write-kubeconfig --cluster=${clustername} --region=${region}'
                sh "ssh -J root@sbs-dev-jump -D 1081 -f root@ruleservice-dev -N"
            }
        }
        stage ("Build and Push Image to ECR") {
            steps {
	      script {
                 if ( env.ENV == "build" || env.ENV == "build & deploy")
                   {
                script {
                    sh """
                        https_proxy=socks5://127.0.0.1:1081 kubectl port-forward service/dind 1337:2375 &
                        sleep 2
                        if docker buildx inspect multiarchbuilder > /dev/null 2>&1; then
                        docker buildx rm multiarchbuilder
                        fi
                        docker buildx create --name multiarchbuilder --node amd64 --platform linux/amd64,linux/aarch64 --driver docker-container --driver-opt env.BUILDKIT_STEP_LOG_MAX_SIZE=10000000 --driver-opt env.BUILDKIT_STEP_LOG_MAX_SPEED=10000000
                        docker buildx create --name multiarchbuilder --append --node arm64 --platform linux/arm64 tcp://127.0.0.1:1337 --driver docker-container --driver-opt env.BUILDKIT_STEP_LOG_MAX_SIZE=10000000 --driver-opt env.BUILDKIT_STEP_LOG_MAX_SPEED=10000000
                        docker buildx inspect --bootstrap --builder multiarchbuilder
                       """
                    sh "docker buildx build --builder multiarchbuilder --platform linux/amd64,linux/aarch64 -t ${registry}:${tag_version} --push ."
                  }
                }
                else {
                sh "echo 'Skipping this step'" 
                }
              }
	    }		    
	  }       
        stage ("Sanitize Workspace") {
            steps {
                cleanWs()
            }

        }
        stage ('Helm checkout') {
            steps {
	        script {
                if ( env.ENV == "build & deploy" || env.ENV == "deploy" )
                {
                checkout scmGit(branches: [[name: '*/main']], extensions: [], userRemoteConfigs: [[credentialsId: 'jenkins-github-token-as-password', url: 'https://github.com/OpenClinica/container-ops.git']])
                }
	 	else {
              sh "echo 'Skipping this step'" 
              }  	
            }
	  }
	}	
        stage('Deploy Helm Chart') {
            steps {
		script {
                if ( env.ENV == "build & deploy" || env.ENV == "deploy" )
                {    
                sh "https_proxy=socks5://127.0.0.1:1081 /usr/local/bin/helm upgrade formdesigner --install apps/kobo_kpi --namespace ${ns} --set kobocat.image.repository=${registry} --set kobocat.image.tag=${tag_version}"
                }
                else {
                sh "echo 'Skipping this step'" 
               }  
	    }
	  }
        }
     }
  }
